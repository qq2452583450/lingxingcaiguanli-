"""Exam center API blueprint."""

from flask import Blueprint, jsonify, request, session

from database.exam_schema import init_exam_schema
from helpers import get_db
from services.exam_service import (
    can_manage_exam,
    can_take_exam,
    DAILY_PRACTICE_QUESTION_COUNT,
    delete_exam_attempt,
    get_attempt,
    get_attempt_review,
    get_current_exam_paper,
    get_daily_practice_status,
    get_exam_paper,
    get_paper_questions,
    list_daily_checkins,
    get_random_practice_questions,
    list_practice_history,
    list_papers,
    list_pending_reviews,
    list_results,
    list_wrong_practice_questions,
    record_practice_answers,
    review_answer,
    start_attempt,
    submit_attempt,
)


exam_bp = Blueprint("exam", __name__, url_prefix="/api/exam")


def _current_user():
    return session.get("user") or {}


def _json_error(message, status_code=400):
    return jsonify({"success": False, "message": message}), status_code


def _require_exam_user():
    user = _current_user()
    if user and (can_take_exam(user) or can_manage_exam(user)):
        return user, None
    return None, _json_error("Permission denied", 403)


def _require_exam_manager():
    user = _current_user()
    if user and can_manage_exam(user):
        return user, None
    return None, _json_error("Permission denied", 403)


def _paper_exists(paper_id):
    return any(paper["id"] == paper_id for paper in list_papers())


def _sanitize_question(question):
    allowed_keys = {
        "id",
        "paper_id",
        "paper_title",
        "question_type",
        "order_no",
        "stem",
        "score",
        "options",
    }
    return {key: value for key, value in question.items() if key in allowed_keys}


def _questions_for_exam_flow(questions):
    return [_sanitize_question(question) for question in questions]


def _filters_from_request():
    filters = {}
    paper_id = request.args.get("paper_id", type=int)
    status = request.args.get("status", "")
    keyword = request.args.get("keyword", "")
    if paper_id:
        filters["paper_id"] = paper_id
    if status:
        filters["status"] = status
    if keyword:
        filters["keyword"] = keyword
    return filters


@exam_bp.route("/summary", methods=["GET"])
def summary():
    user, denied = _require_exam_user()
    if denied:
        return denied

    papers = list_papers()
    return jsonify(
        {
            "success": True,
            "data": {
                "can_take": can_take_exam(user),
                "can_manage": can_manage_exam(user),
                "current_paper": get_current_exam_paper(),
                "paper_count": len(papers),
            },
        }
    )


@exam_bp.route("/practice/random", methods=["GET"])
def random_practice():
    user, denied = _require_exam_user()
    if denied:
        return denied

    limit = request.args.get("limit", default=DAILY_PRACTICE_QUESTION_COUNT, type=int)
    limit = max(1, min(limit or DAILY_PRACTICE_QUESTION_COUNT, 100))
    paper_id = request.args.get("paper_id", type=int)
    questions = get_random_practice_questions(limit=limit, paper_id=paper_id)
    return jsonify({"success": True, "data": _questions_for_exam_flow(questions)})


@exam_bp.route("/practice/submit", methods=["POST"])
def submit_practice():
    user, denied = _require_exam_user()
    if denied:
        return denied
    if not can_take_exam(user):
        return _json_error("Permission denied", 403)

    data = request.get_json(silent=True) or {}
    try:
        result = record_practice_answers(user["id"], data.get("answers") or {})
    except ValueError as exc:
        return _json_error(str(exc), 400)
    return jsonify({"success": True, "data": result})


@exam_bp.route("/practice/daily-status", methods=["GET"])
def practice_daily_status():
    user, denied = _require_exam_user()
    if denied:
        return denied
    if not can_take_exam(user):
        return _json_error("Permission denied", 403)

    return jsonify({"success": True, "data": get_daily_practice_status(user["id"])})


@exam_bp.route("/practice/history", methods=["GET"])
def practice_history():
    user, denied = _require_exam_user()
    if denied:
        return denied
    if not can_take_exam(user):
        return _json_error("Permission denied", 403)

    limit = request.args.get("limit", default=100, type=int)
    limit = max(1, min(limit or 100, 500))
    return jsonify({"success": True, "data": list_practice_history(user["id"], limit=limit)})


@exam_bp.route("/practice/wrong", methods=["GET"])
def wrong_practice():
    user, denied = _require_exam_user()
    if denied:
        return denied
    if not can_take_exam(user):
        return _json_error("Permission denied", 403)

    limit = request.args.get("limit", default=100, type=int)
    limit = max(1, min(limit or 100, 500))
    return jsonify({"success": True, "data": list_wrong_practice_questions(user["id"], limit=limit)})


@exam_bp.route("/papers", methods=["GET"])
def papers():
    _, denied = _require_exam_user()
    if denied:
        return denied

    return jsonify({"success": True, "data": list_papers()})


@exam_bp.route("/attempts", methods=["POST"])
def create_attempt():
    user, denied = _require_exam_user()
    if denied:
        return denied
    if not can_take_exam(user):
        return _json_error("Permission denied", 403)

    current_paper = get_current_exam_paper()
    if not current_paper:
        return _json_error("No current exam paper is set")

    data = request.get_json(silent=True) or {}
    paper_id = data.get("paper_id")
    if paper_id is None:
        paper_id = current_paper["id"]
    try:
        paper_id = int(paper_id)
    except (TypeError, ValueError):
        return _json_error("Invalid paper_id")
    if paper_id != current_paper["id"]:
        return _json_error("Only the current exam paper can be attempted")
    if not _paper_exists(paper_id):
        return _json_error("Paper not found", 404)

    attempt_id = start_attempt(user["id"], paper_id)
    attempt = get_attempt(attempt_id)
    attempt["attempt_id"] = attempt_id
    return jsonify({"success": True, "attempt_id": attempt_id, "data": attempt})


@exam_bp.route("/attempts/<int:attempt_id>", methods=["GET"])
def attempt_detail(attempt_id):
    user, denied = _require_exam_user()
    if denied:
        return denied

    attempt = get_attempt(attempt_id)
    if not attempt:
        return _json_error("Attempt not found", 404)
    if attempt["user_id"] != user.get("id") and not can_manage_exam(user):
        return _json_error("Permission denied", 403)

    questions = get_paper_questions(attempt["paper_id"])
    attempt["questions"] = _questions_for_exam_flow(questions)
    return jsonify({"success": True, "data": attempt})


@exam_bp.route("/attempts/<int:attempt_id>/review", methods=["GET"])
def attempt_review(attempt_id):
    user, denied = _require_exam_user()
    if denied:
        return denied

    attempt = get_attempt(attempt_id)
    if not attempt:
        return _json_error("Attempt not found", 404)
    if attempt["user_id"] != user.get("id") and not can_manage_exam(user):
        return _json_error("Permission denied", 403)
    if attempt["status"] == "in_progress":
        return _json_error("Attempt has not been submitted", 400)

    return jsonify({"success": True, "data": get_attempt_review(attempt_id)})


@exam_bp.route("/attempts/<int:attempt_id>/submit", methods=["POST"])
def submit_attempt_route(attempt_id):
    user, denied = _require_exam_user()
    if denied:
        return denied
    if not can_take_exam(user):
        return _json_error("Permission denied", 403)

    attempt = get_attempt(attempt_id)
    if not attempt:
        return _json_error("Attempt not found", 404)
    if attempt["user_id"] != user.get("id"):
        return _json_error("Permission denied", 403)

    data = request.get_json(silent=True) or {}
    try:
        submit_attempt(attempt_id, data.get("answers") or {})
    except ValueError as exc:
        return _json_error(str(exc), 400)

    return jsonify({"success": True, "data": get_attempt_review(attempt_id)})


@exam_bp.route("/results", methods=["GET"])
def results():
    user, denied = _require_exam_user()
    if denied:
        return denied

    filters = _filters_from_request()
    filters["viewer"] = user
    return jsonify({"success": True, "data": list_results(filters)})


@exam_bp.route("/admin/papers", methods=["GET"])
def admin_papers():
    _, denied = _require_exam_manager()
    if denied:
        return denied

    return jsonify({"success": True, "data": list_papers()})


@exam_bp.route("/admin/current-paper", methods=["POST"])
def set_current_paper():
    _, denied = _require_exam_manager()
    if denied:
        return denied

    data = request.get_json(silent=True) or {}
    try:
        paper_id = int(data.get("paper_id"))
    except (TypeError, ValueError):
        return _json_error("Invalid paper_id")
    paper = get_exam_paper(paper_id)
    if not paper:
        return _json_error("Paper not found", 404)
    if paper["source_type"] != "exam":
        return _json_error("只能设置正式考试卷为当前试卷")

    conn = get_db()
    init_exam_schema(conn)
    conn.execute(
        "INSERT OR REPLACE INTO exam_settings (key, value) VALUES (?, ?)",
        ("current_exam_paper_id", str(paper_id)),
    )
    conn.commit()
    return jsonify({"success": True, "data": get_current_exam_paper()})


@exam_bp.route("/admin/current-paper", methods=["DELETE"])
def clear_current_paper():
    _, denied = _require_exam_manager()
    if denied:
        return denied

    conn = get_db()
    init_exam_schema(conn)
    conn.execute(
        "DELETE FROM exam_settings WHERE key = ?",
        ("current_exam_paper_id",),
    )
    conn.commit()
    return jsonify({"success": True, "data": None})


@exam_bp.route("/admin/results", methods=["GET"])
def admin_results():
    _, denied = _require_exam_manager()
    if denied:
        return denied

    return jsonify({"success": True, "data": list_results(_filters_from_request())})


@exam_bp.route("/admin/checkins", methods=["GET"])
def admin_checkins():
    _, denied = _require_exam_manager()
    if denied:
        return denied

    target_date = request.args.get("date") or None
    return jsonify({"success": True, "data": list_daily_checkins(target_date)})


@exam_bp.route("/admin/attempts/<int:attempt_id>", methods=["DELETE"])
def admin_delete_attempt(attempt_id):
    _, denied = _require_exam_manager()
    if denied:
        return denied

    try:
        delete_exam_attempt(attempt_id)
    except ValueError as exc:
        return _json_error(str(exc), 404)
    return jsonify({"success": True})


@exam_bp.route("/admin/reviews", methods=["GET"])
def admin_reviews():
    _, denied = _require_exam_manager()
    if denied:
        return denied

    return jsonify({"success": True, "data": list_pending_reviews()})


@exam_bp.route("/admin/reviews/<int:answer_id>", methods=["POST"])
def admin_review_answer(answer_id):
    user, denied = _require_exam_manager()
    if denied:
        return denied

    data = request.get_json(silent=True) or {}
    try:
        final_score = float(data.get("final_score"))
    except (TypeError, ValueError):
        return _json_error("Invalid final_score")

    review_answer(answer_id, user["id"], final_score, data.get("comment") or "")
    return jsonify({"success": True})
