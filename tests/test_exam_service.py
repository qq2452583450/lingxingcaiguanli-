from pathlib import Path

import pytest

from services.exam_import_service import import_exam_papers_from_docx, import_exam_papers_from_question_bank_dir
from services.exam_service import (
    can_manage_exam,
    can_take_exam,
    delete_exam_attempt,
    get_daily_practice_status,
    get_attempt,
    get_paper_questions,
    get_random_practice_questions,
    list_daily_checkins,
    list_papers,
    list_practice_history,
    list_pending_reviews,
    list_results,
    list_wrong_practice_questions,
    record_practice_answers,
    retry_wrong_practice_answers,
    list_user_attempts,
    review_answer,
    start_attempt,
    submit_attempt,
    grade_objective,
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


def definitely_wrong_objective_answer(question):
    if question["question_type"] == "multiple_choice":
        correct = set(question["correct_answer"])
        wrong_option = next(
            (option["key"] for option in question.get("options", []) if option["key"] not in correct),
            "Z",
        )
        return question["correct_answer"][:1] + wrong_option
    return "A" if question["correct_answer"] != "A" else "B"


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


def test_daily_random_practice_only_uses_current_five_exam_sets(test_db):
    load_exam(test_db)
    cursor = test_db.cursor()
    cursor.execute(
        """
        INSERT INTO exam_papers (title, duration_minutes, total_score, source_type, create_time)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("旧题库混入卷", 30, 100, "bank", "2026-07-11 00:00:00"),
    )
    old_paper_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO exam_questions (
            paper_id, question_type, order_no, stem, correct_answer, score
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (old_paper_id, "single_choice", 1, "不应该被打卡抽到的旧题", "A", 1),
    )
    old_question_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO exam_question_options (question_id, option_key, option_text)
        VALUES (?, ?, ?)
        """,
        (old_question_id, "A", "旧答案"),
    )
    test_db.commit()

    questions = get_random_practice_questions(limit=200)

    assert questions
    assert "旧题库混入卷" not in {question["paper_title"] for question in questions}
    assert {question["paper_title"] for question in questions} <= {
        "第一套（新编实操版）",
        "第二套（新编案例版）",
        "第三套（新编内控版）",
        "第四套（新编实操易错版）",
        "第五套（新编综合押题版）",
    }


def test_daily_random_practice_uses_current_question_bank_after_reimport(test_db):
    from services.exam_import_service import BUNDLED_QUESTION_BANK_DIR

    import_exam_papers_from_question_bank_dir(BUNDLED_QUESTION_BANK_DIR)

    questions = get_random_practice_questions(limit=30)

    assert len(questions) == 30
    assert all(question["options"] for question in questions)


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


def test_retrying_a_wrong_practice_question_removes_it_without_changing_daily_checkin(test_db):
    paper, _, _ = load_exam(test_db)
    user_id = seed_user(test_db, "wrong_retry", "错题重做", "材料员")
    question = next(
        question
        for question in get_random_practice_questions(limit=20, paper_id=paper["id"])
        if question["question_type"] in {"single_choice", "true_false"}
    )
    wrong_answer = "B" if question["correct_answer"] != "B" else "A"

    record_practice_answers(user_id, {str(question["id"]): wrong_answer})
    daily_before = get_daily_practice_status(user_id)
    result = retry_wrong_practice_answers(
        user_id,
        {str(question["id"]): question["correct_answer"]},
    )

    assert result["items"][0]["is_correct"] is True
    assert result["items"][0]["reference_answer"]
    assert result["resolved_count"] == 1
    assert result["remaining_count"] == 0
    assert list_wrong_practice_questions(user_id) == []
    assert get_daily_practice_status(user_id)["answered_count"] == daily_before["answered_count"]


def test_wrong_practice_records_include_a_fallback_explanation_when_source_has_none(test_db):
    paper, _, _ = load_exam(test_db)
    user_id = seed_user(test_db, "wrong_explanation", "错题解析", "材料员")
    question = next(
        question
        for question in get_random_practice_questions(limit=20, paper_id=paper["id"])
        if question["question_type"] in {"single_choice", "true_false"}
    )
    test_db.execute(
        "UPDATE exam_questions SET reference_answer = '' WHERE id = ?",
        (question["id"],),
    )
    wrong_answer = "B" if question["correct_answer"] != "B" else "A"

    record_practice_answers(user_id, {str(question["id"]): wrong_answer})
    wrong = list_wrong_practice_questions(user_id)

    assert wrong[0]["reference_answer"]
    assert "暂未配置详细解析" not in wrong[0]["reference_answer"]


def test_wrong_practice_records_backfill_real_explanation_from_desktop_question_bank(test_db):
    source_dir = Path.home() / "Desktop" / "\u9898\u5e93"
    if not source_dir.exists():
        pytest.skip("Desktop question bank is not available on this machine")

    import_exam_papers_from_question_bank_dir(source_dir)
    user_id = seed_user(test_db, "wrong_real_explanation", "\u771f\u5b9e\u89e3\u6790", "\u6750\u6599\u5458")
    question = get_paper_questions(list_papers()[0]["id"])[0]
    original_reference = question["reference_answer"]
    test_db.execute(
        "UPDATE exam_questions SET reference_answer = '' WHERE id = ?",
        (question["id"],),
    )
    wrong_answer = "A" if question["correct_answer"] != "A" else "B"

    record_practice_answers(user_id, {str(question["id"]): wrong_answer})
    wrong = list_wrong_practice_questions(user_id)

    assert wrong[0]["reference_answer"] == original_reference


def test_wrong_practice_records_ignore_archived_exam_questions(test_db):
    source_dir = Path.home() / "Desktop" / "\u9898\u5e93"
    if not source_dir.exists():
        pytest.skip("Desktop question bank is not available on this machine")

    paper, _, _ = load_exam(test_db)
    user_id = seed_user(test_db, "archived_wrong", "\u5f52\u6863\u9519\u9898", "\u6750\u6599\u5458")
    question = next(
        question
        for question in get_random_practice_questions(limit=20, paper_id=paper["id"])
        if question["question_type"] in {"single_choice", "true_false"}
    )
    wrong_answer = "B" if question["correct_answer"] != "B" else "A"
    record_practice_answers(user_id, {str(question["id"]): wrong_answer})
    assert list_wrong_practice_questions(user_id)

    import_exam_papers_from_question_bank_dir(source_dir)

    assert list_wrong_practice_questions(user_id) == []


def test_multiple_choice_partial_answer_counts_toward_practice_accuracy(test_db):
    paper, _, _ = load_exam(test_db)
    user_id = seed_user(test_db, "partial_multi", "\u591a\u9009\u6750\u6599\u5458", "\u6750\u6599\u5458")
    question = next(
        question
        for question in get_random_practice_questions(limit=50, paper_id=paper["id"])
        if question["question_type"] == "multiple_choice"
        and len(question["correct_answer"]) >= 2
        and len(question["options"]) > len(set(question["correct_answer"]))
    )
    partial_answer = question["correct_answer"][0]
    wrong_answer = partial_answer + next(
        option["key"] for option in question["options"] if option["key"] not in set(question["correct_answer"])
    )

    partial = record_practice_answers(user_id, {str(question["id"]): partial_answer})
    wrong = record_practice_answers(user_id, {str(question["id"]): wrong_answer})

    expected_credit = round(1 / len(question["correct_answer"]), 4)
    assert grade_objective("multiple_choice", partial_answer, question["correct_answer"], question["score"]) > 0
    assert partial["items"][0]["is_correct"] is False
    assert partial["items"][0]["accuracy_credit"] == expected_credit
    assert partial["accuracy"] == expected_credit
    assert wrong["items"][0]["accuracy_credit"] == 0.0
    assert wrong["accuracy"] == 0.0


def test_multiple_choice_comma_separated_full_answer_scores_full_credit():
    assert grade_objective("multiple_choice", "A,C", "AC", 3) == 3.0
    assert grade_objective("multiple_choice", "A，C", "AC", 3) == 3.0


def test_true_false_scores_symbol_answer_against_chinese_correct_answer():
    assert grade_objective("true_false", "\u221a", "\u6b63\u786e", 1) == 1.0
    assert grade_objective("true_false", "\u00d7", "\u9519\u8bef", 1) == 1.0
    assert grade_objective("true_false", "\u6b63\u786e", "\u221a", 1) == 1.0
    assert grade_objective("true_false", "\u9519\u8bef", "\u00d7", 1) == 1.0


def test_daily_practice_status_passes_at_eighty_percent(test_db):
    paper, _, _ = load_exam(test_db)
    user_id = seed_user(test_db, "daily_clerk", "\u6bcf\u65e5\u6750\u6599\u5458", "\u6750\u6599\u5458")
    questions = get_random_practice_questions(limit=30, paper_id=paper["id"])
    answers = {}
    for index, question in enumerate(questions):
        if index < 24:
            answers[str(question["id"])] = question["correct_answer"]
        else:
            answers[str(question["id"])] = definitely_wrong_objective_answer(question)

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
            answers[str(question["id"])] = definitely_wrong_objective_answer(question)

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


def test_daily_checkins_include_passed_failed_and_not_practiced_takers(test_db):
    paper, _, _ = load_exam(test_db)
    passed_id = seed_user(test_db, "passed_daily", "\u5df2\u5408\u683c", "\u6750\u6599\u5458")
    failed_id = seed_user(test_db, "failed_daily", "\u672a\u5408\u683c", "\u57fa\u5730\u8d1f\u8d23\u4eba")
    missing_id = seed_user(test_db, "missing_daily", "\u672a\u505a\u9898", "\u6750\u6599\u5ba1\u6279\u8d1f\u8d23\u4eba")
    seed_user(test_db, "supplier_daily", "\u4f9b\u5e94\u5546", "\u4f9b\u5e94\u5546")
    questions = get_random_practice_questions(limit=30, paper_id=paper["id"])
    passed_answers = {}
    failed_answers = {}
    for index, question in enumerate(questions):
        wrong = definitely_wrong_objective_answer(question)
        passed_answers[str(question["id"])] = question["correct_answer"] if index < 24 else wrong
        failed_answers[str(question["id"])] = question["correct_answer"] if index < 10 else wrong
    record_practice_answers(passed_id, passed_answers)
    record_practice_answers(failed_id, failed_answers)

    rows = list_daily_checkins()
    by_username = {row["username"]: row for row in rows}

    assert set(by_username) == {"passed_daily", "failed_daily", "missing_daily"}
    assert by_username["passed_daily"]["passed"] is True
    assert by_username["passed_daily"]["practiced"] is True
    assert by_username["passed_daily"]["answered_count"] == 30
    assert by_username["passed_daily"]["best_accuracy"] == 0.8
    assert by_username["failed_daily"]["passed"] is False
    assert by_username["failed_daily"]["practiced"] is True
    assert by_username["failed_daily"]["best_accuracy"] == 0.3333
    assert by_username["missing_daily"]["passed"] is False
    assert by_username["missing_daily"]["practiced"] is False
    assert by_username["missing_daily"]["answered_count"] == 0
    assert by_username["missing_daily"]["latest_practice_at"] is None


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


def test_submit_attempt_scales_weighted_paper_scores_to_one_hundred(test_db):
    user_id = seed_user(test_db, "weighted_clerk", "\u6743\u91cd\u6750\u6599\u5458", "\u6750\u6599\u5458")
    cursor = test_db.cursor()
    cursor.execute(
        """
        INSERT INTO exam_papers (title, duration_minutes, total_score, source_type, create_time)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("Weighted objective paper", 30, 150, "exam", "2026-07-13 00:00:00"),
    )
    paper_id = cursor.lastrowid
    cursor.executemany(
        """
        INSERT INTO exam_questions (
            paper_id, question_type, order_no, stem, correct_answer, score
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (paper_id, "true_false", 1, "判断题", "正确", 5),
            (paper_id, "single_choice", 2, "单选题", "B", 5),
        ],
    )
    test_db.commit()
    attempt_id = start_attempt(user_id, paper_id)

    submit_attempt(attempt_id, {"1": "\u221a", "2": "A"})

    attempt = get_attempt(attempt_id)
    assert attempt["status"] == "completed"
    assert attempt["objective_score"] == 50
    assert attempt["final_score"] == 50


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


def test_delete_exam_attempt_removes_formal_answers_and_reviews_but_keeps_practice(test_db):
    paper, objective, subjective = load_exam(test_db)
    clerk_id = seed_user(test_db, "delete_clerk", "\u5220\u9664\u6750\u6599\u5458", "\u6750\u6599\u5458")
    reviewer_id = seed_user(test_db, "delete_reviewer", "\u5220\u9664\u5ba1\u6279", "\u6750\u6599\u5ba1\u6279\u8d1f\u8d23\u4eba")
    attempt_id = start_attempt(clerk_id, paper["id"])
    submit_attempt(
        attempt_id,
        {
            str(objective["id"]): objective["correct_answer"],
            str(subjective["id"]): subjective["keywords"].split(",")[0],
        },
    )
    pending = list_pending_reviews()
    for row in [item for item in pending if item["attempt_id"] == attempt_id]:
        review_answer(row["answer_id"], reviewer_id, final_score=row["suggested_score"], comment="\u5220\u9664\u6d4b\u8bd5")
    practice_result = record_practice_answers(clerk_id, {str(objective["id"]): objective["correct_answer"]})

    delete_exam_attempt(attempt_id)

    assert get_attempt(attempt_id) is None
    assert test_db.execute("SELECT COUNT(*) FROM exam_answers WHERE attempt_id = ?", (attempt_id,)).fetchone()[0] == 0
    assert test_db.execute("SELECT COUNT(*) FROM exam_subjective_reviews").fetchone()[0] == 0
    assert list_practice_history(clerk_id)[0]["session_id"] == practice_result["session_id"]


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
