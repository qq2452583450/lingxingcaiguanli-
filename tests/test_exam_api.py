from pathlib import Path

import pytest

from services.exam_import_service import import_exam_papers_from_docx
from services.exam_service import get_paper_questions


ROLE_CLERK = "\u6750\u6599\u5458"
ROLE_APPROVAL_OWNER = "\u6750\u6599\u5ba1\u6279\u8d1f\u8d23\u4eba"
ROLE_MANAGER = "\u7cfb\u7edf\u7ba1\u7406\u5458"
ROLE_SUPPLIER = "\u4f9b\u5e94\u5546"
CSRF_TOKEN = "test-token"


@pytest.fixture(autouse=True)
def install_csrf_guard(app):
    from flask import jsonify, request, session

    @app.before_request
    def csrf_protect():
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return
        if request.path in ("/api/login", "/api/supplier/login", "/api/supplier/register"):
            return
        token = request.headers.get("X-CSRF-Token", "")
        if not token or token != session.get("csrf_token", ""):
            return jsonify({"success": False, "message": "CSRF validation failed"}), 403


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


def login(client, user_id, username, real_name, role_name):
    with client.session_transaction() as session:
        session["user"] = {
            "id": user_id,
            "username": username,
            "real_name": real_name,
            "role_name": role_name,
        }
        session["csrf_token"] = CSRF_TOKEN


def csrf_headers():
    return {"X-CSRF-Token": CSRF_TOKEN}


def seed_exam():
    import_exam_papers_from_docx(source_docx())


def select_current_paper(test_db, paper_id=None):
    if paper_id is None:
        paper_id = papers(test_db)[0]["id"]
    test_db.execute(
        "INSERT OR REPLACE INTO exam_settings (key, value) VALUES (?, ?)",
        ("current_exam_paper_id", str(paper_id)),
    )
    test_db.commit()
    return paper_id


def papers(test_db):
    return [
        dict(row)
        for row in test_db.execute(
            "SELECT id, title FROM exam_papers ORDER BY id"
        ).fetchall()
    ]


def definitely_wrong_objective_answer(question, correct):
    if question["question_type"] == "multiple_choice":
        correct_set = set(correct)
        wrong_option = next(
            (option["key"] for option in question.get("options", []) if option["key"] not in correct_set),
            "Z",
        )
        return correct[:1] + wrong_option
    return "A" if correct != "A" else "B"


def assert_question_is_sanitized(question):
    assert "correct_answer" not in question
    assert "reference_answer" not in question
    assert "keywords" not in question
    assert {
        "id",
        "paper_id",
        "question_type",
        "order_no",
        "stem",
        "score",
        "options",
    }.issubset(question.keys())


def test_supplier_cannot_access_exam_summary(client, test_db):
    supplier_id = seed_user(test_db, "supplier", "\u4f9b\u5e94\u5546", ROLE_SUPPLIER)
    login(client, supplier_id, "supplier", "\u4f9b\u5e94\u5546", ROLE_SUPPLIER)

    response = client.get("/api/exam/summary")
    data = response.get_json()

    assert response.status_code == 403
    assert data["success"] is False


def test_material_clerk_can_access_summary_and_random_practice(client, test_db):
    seed_exam()
    current_id = select_current_paper(test_db)
    clerk_id = seed_user(test_db, "clerk", "\u5f20\u6750\u6599", ROLE_CLERK)
    login(client, clerk_id, "clerk", "\u5f20\u6750\u6599", ROLE_CLERK)

    summary = client.get("/api/exam/summary").get_json()
    practice = client.get("/api/exam/practice/random?limit=5").get_json()

    assert summary["success"] is True
    assert summary["data"]["can_manage"] is False
    assert summary["data"]["current_paper"]["id"] == current_id
    assert practice["success"] is True
    assert len(practice["data"]) == 5
    for question in practice["data"]:
        assert_question_is_sanitized(question)
        assert "paper_title" in question


def test_random_practice_defaults_to_daily_thirty_questions(client, test_db):
    seed_exam()
    clerk_id = seed_user(test_db, "daily_default", "\u6bcf\u65e5\u7ec3\u4e60", ROLE_CLERK)
    login(client, clerk_id, "daily_default", "\u6bcf\u65e5\u7ec3\u4e60", ROLE_CLERK)

    practice = client.get("/api/exam/practice/random").get_json()

    assert practice["success"] is True
    assert len(practice["data"]) == 30
    assert {question["question_type"] for question in practice["data"]} <= {
        "single_choice",
        "multiple_choice",
        "true_false",
    }


def test_material_approval_owner_can_access_admin_papers(client, test_db):
    seed_exam()
    owner_id = seed_user(test_db, "owner", "\u5ba1\u6279\u4eba", ROLE_APPROVAL_OWNER)
    login(client, owner_id, "owner", "\u5ba1\u6279\u4eba", ROLE_APPROVAL_OWNER)

    response = client.get("/api/exam/admin/papers")
    data = response.get_json()

    assert response.status_code == 200
    assert data["success"] is True
    assert len(data["data"]) >= 5


def test_manager_can_view_daily_checkin_records(client, test_db):
    from services.exam_service import record_practice_answers

    seed_exam()
    manager_id = seed_user(test_db, "checkin_manager", "\u6253\u5361\u7ba1\u7406", ROLE_MANAGER)
    passed_id = seed_user(test_db, "checkin_passed", "\u5df2\u6253\u5361", ROLE_CLERK)
    missing_id = seed_user(test_db, "checkin_missing", "\u672a\u505a\u9898", ROLE_APPROVAL_OWNER)
    question = next(
        q for q in get_paper_questions(papers(test_db)[0]["id"])
        if q["question_type"] in {"single_choice", "true_false"}
    )
    record_practice_answers(passed_id, {str(question["id"]): question["correct_answer"]})
    login(client, manager_id, "checkin_manager", "\u6253\u5361\u7ba1\u7406", ROLE_MANAGER)

    response = client.get("/api/exam/admin/checkins")
    data = response.get_json()
    by_username = {row["username"]: row for row in data["data"]}

    assert response.status_code == 200
    assert data["success"] is True
    assert {"checkin_passed", "checkin_missing"}.issubset(by_username)
    assert by_username["checkin_passed"]["practiced"] is True
    assert by_username["checkin_missing"]["practiced"] is False


def test_material_clerk_cannot_view_daily_checkin_records(client, test_db):
    seed_exam()
    clerk_id = seed_user(test_db, "checkin_clerk", "\u6750\u6599\u5458", ROLE_CLERK)
    login(client, clerk_id, "checkin_clerk", "\u6750\u6599\u5458", ROLE_CLERK)

    response = client.get("/api/exam/admin/checkins")
    data = response.get_json()

    assert response.status_code == 403
    assert data["success"] is False


def test_material_approval_owner_practice_questions_are_sanitized(client, test_db):
    seed_exam()
    owner_id = seed_user(test_db, "owner", "\u5ba1\u6279\u4eba", ROLE_APPROVAL_OWNER)
    login(client, owner_id, "owner", "\u5ba1\u6279\u4eba", ROLE_APPROVAL_OWNER)

    practice = client.get("/api/exam/practice/random?limit=5").get_json()

    assert practice["success"] is True
    assert len(practice["data"]) == 5
    for question in practice["data"]:
        assert_question_is_sanitized(question)


def test_material_approval_owner_attempt_detail_questions_are_sanitized(client, test_db):
    seed_exam()
    select_current_paper(test_db)
    owner_id = seed_user(test_db, "owner", "\u5ba1\u6279\u4eba", ROLE_APPROVAL_OWNER)
    login(client, owner_id, "owner", "\u5ba1\u6279\u4eba", ROLE_APPROVAL_OWNER)

    start = client.post("/api/exam/attempts", json={}, headers=csrf_headers()).get_json()
    attempt = client.get(f"/api/exam/attempts/{start['attempt_id']}").get_json()

    assert start["success"] is True
    assert attempt["success"] is True
    for question in attempt["data"]["questions"]:
        assert_question_is_sanitized(question)


def test_manager_can_change_current_paper_and_summary_reflects_it(client, test_db):
    seed_exam()
    manager_id = seed_user(test_db, "manager", "\u7ba1\u7406\u5458", ROLE_MANAGER)
    login(client, manager_id, "manager", "\u7ba1\u7406\u5458", ROLE_MANAGER)
    target_paper = papers(test_db)[1]

    change = client.post(
        "/api/exam/admin/current-paper",
        json={"paper_id": target_paper["id"]},
        headers=csrf_headers(),
    ).get_json()
    summary = client.get("/api/exam/summary").get_json()

    assert change["success"] is True
    assert change["data"]["id"] == target_paper["id"]
    assert change["data"]["title"] == target_paper["title"]
    assert summary["success"] is True
    assert summary["data"]["current_paper"]["id"] == target_paper["id"]
    assert summary["data"]["current_paper"]["title"] == target_paper["title"]


def test_manager_can_clear_current_paper_and_summary_hides_formal_exam(client, test_db):
    seed_exam()
    select_current_paper(test_db)
    manager_id = seed_user(test_db, "manager_clear", "\u7ba1\u7406\u5458", ROLE_MANAGER)
    login(client, manager_id, "manager_clear", "\u7ba1\u7406\u5458", ROLE_MANAGER)

    response = client.delete("/api/exam/admin/current-paper", headers=csrf_headers())
    data = response.get_json()
    summary = client.get("/api/exam/summary").get_json()

    assert response.status_code == 200
    assert data["success"] is True
    assert data["data"] is None
    assert summary["success"] is True
    assert summary["data"]["current_paper"] is None


def test_manager_can_clear_current_paper_when_exam_settings_table_is_missing(client, test_db):
    seed_exam()
    manager_id = seed_user(test_db, "manager_clear_missing_table", "\u7ba1\u7406\u5458", ROLE_MANAGER)
    login(client, manager_id, "manager_clear_missing_table", "\u7ba1\u7406\u5458", ROLE_MANAGER)
    test_db.execute("DROP TABLE exam_settings")
    test_db.commit()

    response = client.delete("/api/exam/admin/current-paper", headers=csrf_headers())
    data = response.get_json()

    assert response.status_code == 200
    assert data["success"] is True
    assert data["data"] is None


def test_manager_can_clear_current_paper_without_running_full_exam_schema_migration(client, test_db):
    seed_exam()
    select_current_paper(test_db)
    manager_id = seed_user(test_db, "manager_clear_schema_drift", "\u7ba1\u7406\u5458", ROLE_MANAGER)
    login(client, manager_id, "manager_clear_schema_drift", "\u7ba1\u7406\u5458", ROLE_MANAGER)
    test_db.execute("DROP TABLE IF EXISTS exam_practice_drafts")
    test_db.execute("CREATE VIEW exam_practice_drafts AS SELECT 1 AS id")
    test_db.commit()

    response = client.delete("/api/exam/admin/current-paper", headers=csrf_headers())
    data = response.get_json()

    assert response.status_code == 200
    assert data["success"] is True
    assert data["data"] is None


def test_manager_cannot_set_non_formal_paper_current(client, test_db):
    seed_exam()
    formal_paper_id = select_current_paper(test_db)
    manager_id = seed_user(test_db, "manager", "\u7ba1\u7406\u5458", ROLE_MANAGER)
    login(client, manager_id, "manager", "\u7ba1\u7406\u5458", ROLE_MANAGER)
    cursor = test_db.cursor()
    cursor.execute(
        """
        INSERT INTO exam_papers (
            title, duration_minutes, total_score, source_type, create_time
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("\u9898\u5e93\u53c2\u8003\u5377", 50, 100, "bank", "2026-06-27 00:00:00"),
    )
    bank_paper_id = cursor.lastrowid
    test_db.commit()

    response = client.post(
        "/api/exam/admin/current-paper",
        json={"paper_id": bank_paper_id},
        headers=csrf_headers(),
    )
    data = response.get_json()
    summary = client.get("/api/exam/summary").get_json()

    assert response.status_code == 400
    assert data["success"] is False
    assert "\u6b63\u5f0f\u8003\u8bd5\u5377" in data["message"]
    assert summary["success"] is True
    assert summary["data"]["current_paper"]["id"] == formal_paper_id


def test_clerk_can_start_submit_and_see_own_results(client, test_db):
    seed_exam()
    select_current_paper(test_db)
    clerk_id = seed_user(test_db, "clerk", "\u5f20\u6750\u6599", ROLE_CLERK)
    login(client, clerk_id, "clerk", "\u5f20\u6750\u6599", ROLE_CLERK)
    current_paper = papers(test_db)[0]
    questions = get_paper_questions(current_paper["id"])
    objective = next(q for q in questions if q["question_type"] in {"single_choice", "multiple_choice", "true_false"})
    subjective = next(q for q in questions if q["question_type"] in {"short_answer", "case_analysis"})

    start = client.post("/api/exam/attempts", json={}, headers=csrf_headers()).get_json()
    attempt_id = start["attempt_id"]
    attempt = client.get(f"/api/exam/attempts/{attempt_id}").get_json()
    submit = client.post(
        f"/api/exam/attempts/{attempt_id}/submit",
        json={
            "answers": {
                str(objective["id"]): objective["correct_answer"],
                str(subjective["id"]): subjective["keywords"].split(",")[0],
            }
        },
        headers=csrf_headers(),
    ).get_json()
    results = client.get("/api/exam/results").get_json()

    assert start["success"] is True
    assert start["data"]["attempt_id"] == attempt_id
    assert attempt["success"] is True
    assert attempt["data"]["id"] == attempt_id
    for question in attempt["data"]["questions"]:
        assert_question_is_sanitized(question)
        assert "paper_title" not in question
    assert submit["success"] is True
    assert submit["data"]["attempt"]["id"] == attempt_id
    assert submit["data"]["items"]
    assert any("correct_answer" in item or "reference_answer" in item for item in submit["data"]["items"])
    assert results["success"] is True
    assert [row["attempt_id"] for row in results["data"]] == [attempt_id]


def test_clerk_cannot_start_attempt_for_non_current_paper(client, test_db):
    seed_exam()
    select_current_paper(test_db)
    clerk_id = seed_user(test_db, "clerk", "\u5f20\u6750\u6599", ROLE_CLERK)
    login(client, clerk_id, "clerk", "\u5f20\u6750\u6599", ROLE_CLERK)
    non_current_paper = papers(test_db)[1]

    response = client.post(
        "/api/exam/attempts",
        json={"paper_id": non_current_paper["id"]},
        headers=csrf_headers(),
    )
    data = response.get_json()
    attempts_for_paper = test_db.execute(
        "SELECT COUNT(*) AS count FROM exam_attempts WHERE paper_id = ?",
        (non_current_paper["id"],),
    ).fetchone()["count"]

    assert response.status_code == 400
    assert data["success"] is False
    assert attempts_for_paper == 0


def test_clerk_cannot_start_formal_exam_before_manager_selects_current_paper(client, test_db):
    seed_exam()
    clerk_id = seed_user(test_db, "no_current", "\u672a\u9009\u8bd5\u5377", ROLE_CLERK)
    login(client, clerk_id, "no_current", "\u672a\u9009\u8bd5\u5377", ROLE_CLERK)

    summary = client.get("/api/exam/summary").get_json()
    response = client.post("/api/exam/attempts", json={}, headers=csrf_headers())
    data = response.get_json()

    assert summary["success"] is True
    assert summary["data"]["current_paper"] is None
    assert response.status_code == 400
    assert data["success"] is False
    assert "current exam paper" in data["message"]
    assert test_db.execute("SELECT COUNT(*) FROM exam_attempts").fetchone()[0] == 0


def test_exam_attempt_post_without_csrf_token_is_rejected(client, test_db):
    seed_exam()
    select_current_paper(test_db)
    clerk_id = seed_user(test_db, "clerk", "\u5f20\u6750\u6599", ROLE_CLERK)
    login(client, clerk_id, "clerk", "\u5f20\u6750\u6599", ROLE_CLERK)

    response = client.post("/api/exam/attempts", json={})
    data = response.get_json()

    assert response.status_code == 403
    assert data["success"] is False


def test_duplicate_submission_returns_non_success_response(client, test_db):
    seed_exam()
    select_current_paper(test_db)
    clerk_id = seed_user(test_db, "clerk", "\u5f20\u6750\u6599", ROLE_CLERK)
    login(client, clerk_id, "clerk", "\u5f20\u6750\u6599", ROLE_CLERK)
    current_paper = papers(test_db)[0]
    objective = next(
        q
        for q in get_paper_questions(current_paper["id"])
        if q["question_type"] in {"single_choice", "multiple_choice", "true_false"}
    )
    start = client.post("/api/exam/attempts", json={}, headers=csrf_headers()).get_json()
    attempt_id = start["attempt_id"]
    answer_payload = {"answers": {str(objective["id"]): objective["correct_answer"]}}

    first = client.post(
        f"/api/exam/attempts/{attempt_id}/submit",
        json=answer_payload,
        headers=csrf_headers(),
    ).get_json()
    duplicate_response = client.post(
        f"/api/exam/attempts/{attempt_id}/submit",
        json=answer_payload,
        headers=csrf_headers(),
    )
    duplicate = duplicate_response.get_json()

    assert first["success"] is True
    assert duplicate_response.status_code == 400
    assert duplicate["success"] is False


def test_practice_submit_returns_answers_and_persists_history(client, test_db):
    seed_exam()
    clerk_id = seed_user(test_db, "practice_api", "\u7ec3\u4e60\u63a5\u53e3", ROLE_CLERK)
    login(client, clerk_id, "practice_api", "\u7ec3\u4e60\u63a5\u53e3", ROLE_CLERK)
    practice = client.get("/api/exam/practice/random?limit=10").get_json()
    question = next(
        q for q in practice["data"]
        if q["question_type"] in {"single_choice", "true_false"}
    )
    correct = test_db.execute(
        "SELECT correct_answer FROM exam_questions WHERE id = ?",
        (question["id"],),
    ).fetchone()["correct_answer"]

    submit = client.post(
        "/api/exam/practice/submit",
        json={"answers": {str(question["id"]): correct}},
        headers=csrf_headers(),
    ).get_json()
    history = client.get("/api/exam/practice/history").get_json()

    assert submit["success"] is True
    assert submit["data"]["items"][0]["correct_answer"] == correct
    assert submit["data"]["items"][0]["is_correct"] is True
    assert history["success"] is True
    assert history["data"][0]["question_id"] == question["id"]


def test_practice_draft_can_be_saved_and_restored_without_checkin(client, test_db):
    seed_exam()
    clerk_id = seed_user(test_db, "practice_draft", "\u7ec3\u4e60\u6682\u5b58", ROLE_CLERK)
    login(client, clerk_id, "practice_draft", "\u7ec3\u4e60\u6682\u5b58", ROLE_CLERK)
    practice = client.get("/api/exam/practice/random?limit=5").get_json()
    question_ids = [question["id"] for question in practice["data"]]
    first_question = practice["data"][0]
    answer = first_question["options"][0]["key"]

    saved = client.put(
        "/api/exam/practice/draft",
        json={
            "question_ids": question_ids,
            "answers": {str(first_question["id"]): answer},
        },
        headers=csrf_headers(),
    ).get_json()
    restored = client.get("/api/exam/practice/draft").get_json()
    status = client.get("/api/exam/practice/daily-status").get_json()

    assert saved["success"] is True
    assert restored["success"] is True
    assert [question["id"] for question in restored["data"]["questions"]] == question_ids
    for question in restored["data"]["questions"]:
        assert_question_is_sanitized(question)
    assert restored["data"]["answers"][str(first_question["id"])] == answer
    assert status["data"]["answered_count"] == 0
    assert status["data"]["session_count"] == 0


def test_practice_submit_clears_saved_draft(client, test_db):
    seed_exam()
    clerk_id = seed_user(test_db, "practice_draft_submit", "\u6682\u5b58\u63d0\u4ea4", ROLE_CLERK)
    login(client, clerk_id, "practice_draft_submit", "\u6682\u5b58\u63d0\u4ea4", ROLE_CLERK)
    practice = client.get("/api/exam/practice/random?limit=5").get_json()
    question = practice["data"][0]
    correct = test_db.execute(
        "SELECT correct_answer FROM exam_questions WHERE id = ?",
        (question["id"],),
    ).fetchone()["correct_answer"]
    client.put(
        "/api/exam/practice/draft",
        json={"question_ids": [question["id"]], "answers": {str(question["id"]): correct}},
        headers=csrf_headers(),
    )

    submit = client.post(
        "/api/exam/practice/submit",
        json={"answers": {str(question["id"]): correct}},
        headers=csrf_headers(),
    ).get_json()
    restored = client.get("/api/exam/practice/draft").get_json()

    assert submit["success"] is True
    assert restored["success"] is True
    assert restored["data"] is None


def test_formal_exam_has_no_draft_endpoint(client, test_db):
    seed_exam()
    select_current_paper(test_db)
    clerk_id = seed_user(test_db, "formal_no_draft", "\u6b63\u5f0f\u65e0\u6682\u5b58", ROLE_CLERK)
    login(client, clerk_id, "formal_no_draft", "\u6b63\u5f0f\u65e0\u6682\u5b58", ROLE_CLERK)
    start = client.post("/api/exam/attempts", json={}, headers=csrf_headers()).get_json()

    response = client.post(
        f"/api/exam/attempts/{start['attempt_id']}/draft",
        json={"answers": {}},
        headers=csrf_headers(),
    )

    assert response.status_code == 404


def test_practice_submit_returns_daily_pass_status(client, test_db):
    seed_exam()
    clerk_id = seed_user(test_db, "daily_submit", "\u6253\u5361\u63d0\u4ea4", ROLE_CLERK)
    login(client, clerk_id, "daily_submit", "\u6253\u5361\u63d0\u4ea4", ROLE_CLERK)
    practice = client.get("/api/exam/practice/random?limit=30").get_json()
    correct_answers = {
        row["id"]: row["correct_answer"]
        for row in test_db.execute(
            "SELECT id, correct_answer FROM exam_questions"
        ).fetchall()
    }
    answers = {}
    for index, question in enumerate(practice["data"]):
        correct = correct_answers[question["id"]]
        answers[str(question["id"])] = correct if index < 24 else definitely_wrong_objective_answer(question, correct)

    submit = client.post(
        "/api/exam/practice/submit",
        json={"answers": answers},
        headers=csrf_headers(),
    ).get_json()
    status = client.get("/api/exam/practice/daily-status").get_json()

    assert submit["success"] is True
    assert submit["data"]["total_count"] == 30
    assert submit["data"]["correct_count"] == 24
    assert submit["data"]["accuracy"] == 0.8
    assert submit["data"]["required_accuracy"] == 0.8
    assert submit["data"]["passed"] is True
    assert submit["data"]["daily_status"]["passed"] is True
    assert status["success"] is True
    assert status["data"]["passed"] is True
    assert status["data"]["answered_count"] == 30


def test_wrong_practice_endpoint_scopes_to_current_user(client, test_db):
    from services.exam_service import record_practice_answers

    seed_exam()
    clerk_id = seed_user(test_db, "wrong_api", "\u9519\u9898\u63a5\u53e3", ROLE_CLERK)
    other_id = seed_user(test_db, "other_wrong_api", "\u5176\u4ed6\u6750\u6599\u5458", ROLE_CLERK)
    question = next(
        q for q in get_paper_questions(papers(test_db)[0]["id"])
        if q["question_type"] in {"single_choice", "true_false"}
    )
    wrong_answer = "B" if question["correct_answer"] != "B" else "A"
    record_practice_answers(clerk_id, {str(question["id"]): wrong_answer})
    record_practice_answers(other_id, {str(question["id"]): wrong_answer})
    login(client, clerk_id, "wrong_api", "\u9519\u9898\u63a5\u53e3", ROLE_CLERK)

    data = client.get("/api/exam/practice/wrong").get_json()

    assert data["success"] is True
    assert len(data["data"]) == 1
    assert data["data"][0]["question_id"] == question["id"]


def test_wrong_practice_can_be_retried_and_is_removed_after_a_correct_answer(client, test_db):
    from services.exam_service import record_practice_answers

    seed_exam()
    clerk_id = seed_user(test_db, "wrong_retry_api", "错题重做接口", ROLE_CLERK)
    question = next(
        q for q in get_paper_questions(papers(test_db)[0]["id"])
        if q["question_type"] in {"single_choice", "true_false"}
    )
    wrong_answer = "B" if question["correct_answer"] != "B" else "A"
    record_practice_answers(clerk_id, {str(question["id"]): wrong_answer})
    login(client, clerk_id, "wrong_retry_api", "错题重做接口", ROLE_CLERK)

    retry_questions = client.get("/api/exam/practice/wrong/questions").get_json()
    retry = client.post(
        "/api/exam/practice/wrong/submit",
        json={"answers": {str(question["id"]): question["correct_answer"]}},
        headers=csrf_headers(),
    ).get_json()
    remaining = client.get("/api/exam/practice/wrong").get_json()

    assert retry_questions["success"] is True
    assert_question_is_sanitized(retry_questions["data"][0])
    assert retry["success"] is True
    assert retry["data"]["items"][0]["reference_answer"] == question["reference_answer"]
    assert retry["data"]["resolved_count"] == 1
    assert retry["data"]["remaining_count"] == 0
    assert remaining["data"] == []


def test_attempt_review_returns_answer_details_for_owner_only(client, test_db):
    seed_exam()
    select_current_paper(test_db)
    clerk_id = seed_user(test_db, "review_owner", "\u56de\u770b\u672c\u4eba", ROLE_CLERK)
    other_id = seed_user(test_db, "review_other", "\u5176\u4ed6\u4eba\u5458", ROLE_CLERK)
    login(client, clerk_id, "review_owner", "\u56de\u770b\u672c\u4eba", ROLE_CLERK)
    current_paper = papers(test_db)[0]
    objective = next(
        q for q in get_paper_questions(current_paper["id"])
        if q["question_type"] in {"single_choice", "true_false"}
    )
    start = client.post("/api/exam/attempts", json={}, headers=csrf_headers()).get_json()
    attempt_id = start["attempt_id"]
    client.post(
        f"/api/exam/attempts/{attempt_id}/submit",
        json={"answers": {str(objective["id"]): objective["correct_answer"]}},
        headers=csrf_headers(),
    )

    owner_review = client.get(f"/api/exam/attempts/{attempt_id}/review").get_json()
    login(client, other_id, "review_other", "\u5176\u4ed6\u4eba\u5458", ROLE_CLERK)
    other_response = client.get(f"/api/exam/attempts/{attempt_id}/review")

    assert owner_review["success"] is True
    assert owner_review["data"]["attempt"]["id"] == attempt_id
    assert owner_review["data"]["items"][0]["answer_text"] == objective["correct_answer"]
    assert owner_review["data"]["items"][0]["correct_answer"] == objective["correct_answer"]
    assert other_response.status_code == 403


def test_manager_can_delete_exam_attempt_result(client, test_db):
    seed_exam()
    select_current_paper(test_db)
    manager_id = seed_user(test_db, "delete_manager", "\u5220\u9664\u7ba1\u7406", ROLE_MANAGER)
    clerk_id = seed_user(test_db, "delete_api_clerk", "\u5220\u9664\u5458", ROLE_CLERK)
    login(client, clerk_id, "delete_api_clerk", "\u5220\u9664\u5458", ROLE_CLERK)
    current_paper = papers(test_db)[0]
    objective = next(
        q for q in get_paper_questions(current_paper["id"])
        if q["question_type"] in {"single_choice", "true_false"}
    )
    start = client.post("/api/exam/attempts", json={}, headers=csrf_headers()).get_json()
    attempt_id = start["attempt_id"]
    client.post(
        f"/api/exam/attempts/{attempt_id}/submit",
        json={"answers": {str(objective["id"]): objective["correct_answer"]}},
        headers=csrf_headers(),
    )
    login(client, manager_id, "delete_manager", "\u5220\u9664\u7ba1\u7406", ROLE_MANAGER)

    response = client.delete(
        f"/api/exam/admin/attempts/{attempt_id}",
        headers=csrf_headers(),
    )
    data = response.get_json()
    results = client.get("/api/exam/admin/results").get_json()

    assert response.status_code == 200
    assert data["success"] is True
    assert attempt_id not in {row["attempt_id"] for row in results["data"]}


def test_material_clerk_cannot_delete_exam_attempt_result(client, test_db):
    seed_exam()
    select_current_paper(test_db)
    clerk_id = seed_user(test_db, "delete_denied_clerk", "\u666e\u901a\u6750\u6599\u5458", ROLE_CLERK)
    login(client, clerk_id, "delete_denied_clerk", "\u666e\u901a\u6750\u6599\u5458", ROLE_CLERK)
    current_paper = papers(test_db)[0]
    objective = next(
        q for q in get_paper_questions(current_paper["id"])
        if q["question_type"] in {"single_choice", "true_false"}
    )
    start = client.post("/api/exam/attempts", json={}, headers=csrf_headers()).get_json()
    attempt_id = start["attempt_id"]

    response = client.delete(
        f"/api/exam/admin/attempts/{attempt_id}",
        headers=csrf_headers(),
    )
    data = response.get_json()

    assert response.status_code == 403
    assert data["success"] is False
