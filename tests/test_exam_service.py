from pathlib import Path

import pytest

from services.exam_import_service import import_exam_papers_from_docx
from services.exam_service import (
    can_manage_exam,
    can_take_exam,
    get_daily_practice_status,
    get_attempt,
    get_paper_questions,
    get_random_practice_questions,
    list_practice_history,
    list_pending_reviews,
    list_results,
    list_wrong_practice_questions,
    record_practice_answers,
    list_user_attempts,
    review_answer,
    start_attempt,
    submit_attempt,
)


def source_docx():
    return next(Path("docs/exam_sources").glob("*\u6750\u6599\u8fdb\u573a\u9a8c\u6536\u6807\u51c6\u4e13\u9879\u8003\u8bd5\u5377*.docx"))


def seed_user(test_db, username, real_name, role_name):
    cursor = test_db.cursor()
    cursor.execute("SELECT id FROM roles WHERE role_name = ?", (role_name,))
    role = cursor.fetchone()
    if role:
        role_id = role["id"]
    else:
        cursor.execute(
            "INSERT INTO roles (role_name, permissions) VALUES (?, ?)",
            (role_name, ""),
        )
        role_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (username, "password", real_name, role_id, 1, "2026-06-26 00:00:00"),
    )
    test_db.commit()
    return cursor.lastrowid


def load_exam(test_db):
    import_exam_papers_from_docx(source_docx())
    paper = test_db.execute(
        "SELECT id, title FROM exam_papers ORDER BY id LIMIT 1"
    ).fetchone()
    questions = get_paper_questions(paper["id"])
    objective = next(q for q in questions if q["question_type"] in {"single_choice", "multiple_choice", "true_false"})
    subjective = next(q for q in questions if q["question_type"] in {"short_answer", "case_analysis"})
    return dict(paper), objective, subjective


def test_role_permissions_for_takers_managers_and_supplier_exclusion():
    assert can_take_exam({"role_name": "\u6750\u6599\u5458"})
    assert can_take_exam({"role_name": "\u6750\u6599\u5ba1\u6279\u8d1f\u8d23\u4eba"})
    assert can_take_exam({"role_name": "\u57fa\u5730\u8d1f\u8d23\u4eba"})
    assert not can_take_exam({"role_name": "\u4f9b\u5e94\u5546"})

    assert can_manage_exam({"role_name": "\u7cfb\u7edf\u7ba1\u7406\u5458"})
    assert can_manage_exam({"role_name": "\u6750\u6599\u5ba1\u6279\u8d1f\u8d23\u4eba"})
    assert not can_manage_exam({"role_name": "\u6750\u6599\u5458"})
    assert not can_manage_exam({"role_name": "\u4f9b\u5e94\u5546"})


def test_random_practice_returns_requested_count_with_options_after_import(test_db):
    paper, _, _ = load_exam(test_db)

    questions = get_random_practice_questions(limit=5, paper_id=paper["id"])

    assert len(questions) == 5
    assert {question["paper_id"] for question in questions} == {paper["id"]}
    assert {question["paper_title"] for question in questions} == {paper["title"]}
    assert all("options" in question for question in questions)
    assert any(question["options"] for question in questions)


def test_random_practice_excludes_subjective_questions(test_db):
    paper, _, _ = load_exam(test_db)

    questions = get_random_practice_questions(limit=50, paper_id=paper["id"])

    assert questions
    assert {question["question_type"] for question in questions} <= {
        "single_choice",
        "multiple_choice",
        "true_false",
    }


def test_record_practice_answers_scores_and_lists_history(test_db):
    paper, _, _ = load_exam(test_db)
    user_id = seed_user(test_db, "practice_clerk", "\u7ec3\u4e60\u6750\u6599\u5458", "\u6750\u6599\u5458")
    objective = next(
        question
        for question in get_random_practice_questions(limit=20, paper_id=paper["id"])
        if question["question_type"] in {"single_choice", "true_false"}
    )
    wrong_answer = "B" if objective["correct_answer"] != "B" else "A"

    result = record_practice_answers(user_id, {str(objective["id"]): wrong_answer})
    history = list_practice_history(user_id)
    wrong = list_wrong_practice_questions(user_id)

    assert result["session_id"]
    assert result["items"][0]["question_id"] == objective["id"]
    assert result["items"][0]["answer_text"] == wrong_answer
    assert result["items"][0]["correct_answer"] == objective["correct_answer"]
    assert result["items"][0]["is_correct"] is False
    assert history[0]["session_id"] == result["session_id"]
    assert wrong[0]["question_id"] == objective["id"]


def test_daily_practice_status_passes_at_eighty_percent(test_db):
    paper, _, _ = load_exam(test_db)
    user_id = seed_user(test_db, "daily_clerk", "\u6bcf\u65e5\u6750\u6599\u5458", "\u6750\u6599\u5458")
    questions = get_random_practice_questions(limit=30, paper_id=paper["id"])
    answers = {}
    for index, question in enumerate(questions):
        if index < 24:
            answers[str(question["id"])] = question["correct_answer"]
        else:
            answers[str(question["id"])] = "A" if question["correct_answer"] != "A" else "B"

    result = record_practice_answers(user_id, answers)
    status = get_daily_practice_status(user_id)

    assert result["total_count"] == 30
    assert result["correct_count"] == 24
    assert result["accuracy"] == 0.8
    assert result["required_accuracy"] == 0.8
    assert result["passed"] is True
    assert result["daily_status"]["passed"] is True
    assert status["passed"] is True
    assert status["best_accuracy"] == 0.8
    assert status["session_count"] == 1
    assert status["answered_count"] == 30


def test_daily_practice_status_requires_continued_practice_below_eighty_percent(test_db):
    paper, _, _ = load_exam(test_db)
    user_id = seed_user(test_db, "daily_retry", "\u672a\u8fbe\u6807\u6750\u6599\u5458", "\u6750\u6599\u5458")
    questions = get_random_practice_questions(limit=30, paper_id=paper["id"])
    answers = {}
    for index, question in enumerate(questions):
        if index < 23:
            answers[str(question["id"])] = question["correct_answer"]
        else:
            answers[str(question["id"])] = "A" if question["correct_answer"] != "A" else "B"

    result = record_practice_answers(user_id, answers)
    status = get_daily_practice_status(user_id)

    assert result["total_count"] == 30
    assert result["correct_count"] == 23
    assert result["accuracy"] == 0.7667
    assert result["passed"] is False
    assert result["daily_status"]["passed"] is False
    assert status["passed"] is False
    assert status["best_accuracy"] == 0.7667
    assert status["session_count"] == 1
    assert status["answered_count"] == 30


def test_submit_attempt_scores_objective_and_leaves_subjective_pending_review(test_db):
    paper, objective, subjective = load_exam(test_db)
    user_id = seed_user(test_db, "clerk", "\u6750\u6599\u5458", "\u6750\u6599\u5458")
    attempt_id = start_attempt(user_id, paper["id"])
    objective_only_attempt_id = start_attempt(user_id, paper["id"])

    submit_attempt(
        attempt_id,
        {
            str(objective["id"]): objective["correct_answer"],
            str(subjective["id"]): subjective["keywords"].split(",")[0],
        },
    )

    attempt = get_attempt(attempt_id)
    objective_answer = test_db.execute(
        "SELECT auto_score, final_score FROM exam_answers WHERE attempt_id = ? AND question_id = ?",
        (attempt_id, objective["id"]),
    ).fetchone()
    subjective_answer = test_db.execute(
        "SELECT suggested_score, final_score FROM exam_answers WHERE attempt_id = ? AND question_id = ?",
        (attempt_id, subjective["id"]),
    ).fetchone()

    assert attempt["status"] == "pending_review"
    assert attempt["objective_score"] == objective["score"]
    assert attempt["suggested_subjective_score"] > 0
    assert attempt["final_score"] is None
    assert objective_answer["auto_score"] == objective["score"]
    assert objective_answer["final_score"] == objective["score"]
    assert subjective_answer["suggested_score"] > 0
    assert subjective_answer["final_score"] is None

    submit_attempt(
        objective_only_attempt_id,
        {str(objective["id"]): objective["correct_answer"]},
    )
    objective_only_attempt = get_attempt(objective_only_attempt_id)
    missing_subjective_answer = test_db.execute(
        "SELECT answer_text, suggested_score, final_score FROM exam_answers WHERE attempt_id = ? AND question_id = ?",
        (objective_only_attempt_id, subjective["id"]),
    ).fetchone()

    assert objective_only_attempt["status"] == "pending_review"
    assert objective_only_attempt["final_score"] is None
    assert missing_subjective_answer["answer_text"] == ""
    assert missing_subjective_answer["suggested_score"] == 0
    assert missing_subjective_answer["final_score"] is None


def test_review_answer_completes_attempt_and_results_scope_by_viewer(test_db):
    paper, objective, subjective = load_exam(test_db)
    clerk_id = seed_user(test_db, "clerk", "\u5f20\u6750\u6599", "\u6750\u6599\u5458")
    other_clerk_id = seed_user(test_db, "other", "\u674e\u6750\u6599", "\u6750\u6599\u5458")
    reviewer_id = seed_user(test_db, "reviewer", "\u5ba1\u6279\u4eba", "\u6750\u6599\u5ba1\u6279\u8d1f\u8d23\u4eba")
    attempt_id = start_attempt(clerk_id, paper["id"])
    other_attempt_id = start_attempt(other_clerk_id, paper["id"])
    submit_attempt(
        attempt_id,
        {
            str(objective["id"]): objective["correct_answer"],
            str(subjective["id"]): subjective["keywords"].split(",")[0],
        },
    )
    submit_attempt(other_attempt_id, {str(objective["id"]): objective["correct_answer"]})
    pending = list_pending_reviews()
    pending_for_attempt = [row for row in pending if row["attempt_id"] == attempt_id]

    for row in pending_for_attempt:
        review_answer(
            row["answer_id"],
            reviewer_id,
            final_score=subjective["score"] if row["question_id"] == subjective["id"] else 0,
            comment="\u901a\u8fc7",
        )

    attempt = get_attempt(attempt_id)
    user_attempts = list_user_attempts(clerk_id)
    manager_results = list_results({"viewer": {"id": reviewer_id, "role_name": "\u6750\u6599\u5ba1\u6279\u8d1f\u8d23\u4eba"}})
    clerk_results = list_results({"viewer": {"id": clerk_id, "role_name": "\u6750\u6599\u5458"}})

    assert attempt["status"] == "completed"
    assert attempt["final_subjective_score"] == subjective["score"]
    assert attempt["final_score"] == objective["score"] + subjective["score"]
    assert [row["id"] for row in user_attempts] == [attempt_id]
    assert user_attempts[0]["paper_title"] == paper["title"]
    assert {row["attempt_id"] for row in manager_results} == {attempt_id, other_attempt_id}
    assert {row["attempt_id"] for row in clerk_results} == {attempt_id}
    assert manager_results[0]["user_name"]
    assert manager_results[0]["username"]
    assert manager_results[0]["role_name"]
    assert manager_results[0]["paper_title"] == paper["title"]


def test_submit_attempt_rejects_duplicate_submission_without_resetting_scores(test_db):
    paper, objective, subjective = load_exam(test_db)
    clerk_id = seed_user(test_db, "clerk", "\u5f20\u6750\u6599", "\u6750\u6599\u5458")
    reviewer_id = seed_user(test_db, "reviewer", "\u5ba1\u6279\u4eba", "\u6750\u6599\u5ba1\u6279\u8d1f\u8d23\u4eba")
    pending_attempt_id = start_attempt(clerk_id, paper["id"])
    completed_attempt_id = start_attempt(clerk_id, paper["id"])

    submit_attempt(
        pending_attempt_id,
        {
            str(objective["id"]): objective["correct_answer"],
            str(subjective["id"]): subjective["keywords"].split(",")[0],
        },
    )
    with pytest.raises(ValueError, match="\u4e0d\u80fd\u91cd\u590d\u4ea4\u5377"):
        submit_attempt(pending_attempt_id, {str(objective["id"]): ""})
    assert get_attempt(pending_attempt_id)["status"] == "pending_review"

    submit_attempt(
        completed_attempt_id,
        {
            str(objective["id"]): objective["correct_answer"],
            str(subjective["id"]): subjective["keywords"].split(",")[0],
        },
    )
    for row in [row for row in list_pending_reviews() if row["attempt_id"] == completed_attempt_id]:
        review_answer(
            row["answer_id"],
            reviewer_id,
            final_score=subjective["score"] if row["question_id"] == subjective["id"] else 0,
            comment="\u901a\u8fc7",
        )
    completed_attempt = get_attempt(completed_attempt_id)
    reviewed_subjective_answer = test_db.execute(
        "SELECT final_score FROM exam_answers WHERE attempt_id = ? AND question_id = ?",
        (completed_attempt_id, subjective["id"]),
    ).fetchone()

    with pytest.raises(ValueError, match="\u4e0d\u80fd\u91cd\u590d\u4ea4\u5377"):
        submit_attempt(completed_attempt_id, {str(objective["id"]): ""})

    preserved_attempt = get_attempt(completed_attempt_id)
    preserved_subjective_answer = test_db.execute(
        "SELECT final_score FROM exam_answers WHERE attempt_id = ? AND question_id = ?",
        (completed_attempt_id, subjective["id"]),
    ).fetchone()
    assert completed_attempt["status"] == "completed"
    assert preserved_attempt["status"] == "completed"
    assert preserved_attempt["final_score"] == completed_attempt["final_score"]
    assert preserved_subjective_answer["final_score"] == reviewed_subjective_answer["final_score"]
