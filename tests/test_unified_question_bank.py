from pathlib import Path

from services.exam_import_service import (
    parse_literature_question_bank_docx,
    replace_active_practice_sources_with_unified_question_bank,
)
from services.exam_service import get_random_practice_questions


SOURCE = Path("docs/exam_sources/unified_question_bank/物资管理题库汇编（220题）.docx")


def test_unified_bank_parses_all_220_questions_and_keeps_e_options():
    bank = parse_literature_question_bank_docx(SOURCE)

    assert len(bank["questions"]) == 220
    assert set(question["question_type"] for question in bank["questions"]) == {
        "single_choice", "multiple_choice", "true_false"
    }
    assert sum(
        1 for question in bank["questions"]
        if any(option["key"] == "E" for option in question["options"])
    ) == 44


def test_replacement_archives_old_practice_papers_and_resets_practice_state(test_db):
    cursor = test_db.cursor()
    cursor.execute(
        "INSERT INTO exam_papers (title, duration_minutes, total_score, source_type, create_time) VALUES (?, 50, 100, 'exam', ?)",
        ("第一套（新编实操版）", "2026-09-08 08:00:00"),
    )
    old_paper_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO exam_questions (paper_id, question_type, order_no, stem, correct_answer, score) VALUES (?, 'single_choice', 1, '旧题', 'A', 2)",
        (old_paper_id,),
    )
    old_question_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO exam_practice_wrong_questions (user_id, question_id, wrong_count, last_answer_text, first_wrong_at, last_wrong_at) VALUES (1, ?, 1, 'B', ?, ?)",
        (old_question_id, "2026-09-08 08:00:00", "2026-09-08 08:00:00"),
    )
    cursor.execute(
        "INSERT INTO exam_practice_drafts (user_id, question_ids, answers_json, updated_at) VALUES (1, '[1]', '{}', ?)",
        ("2026-09-08 08:00:00",),
    )
    cursor.execute(
        "INSERT INTO exam_papers (title, duration_minutes, total_score, source_type, create_time) VALUES (?, 50, 100, 'exam', ?)",
        ("综合题库四（满分 100 分）", "2026-09-08 08:00:00"),
    )
    formal_paper_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO exam_settings (key, value) VALUES ('current_exam_paper_id', ?)",
        (str(formal_paper_id),),
    )
    test_db.commit()

    result = replace_active_practice_sources_with_unified_question_bank(conn=test_db)
    test_db.commit()

    assert result["bank_question_count"] == 220
    assert result["archived_papers"] == 1
    assert test_db.execute("SELECT source_type FROM exam_papers WHERE id = ?", (old_paper_id,)).fetchone()[0] == "archived_exam"
    assert test_db.execute("SELECT source_type FROM exam_papers WHERE id = ?", (formal_paper_id,)).fetchone()[0] == "exam"
    assert test_db.execute("SELECT value FROM exam_settings WHERE key = 'current_exam_paper_id'").fetchone()[0] == str(formal_paper_id)
    assert test_db.execute("SELECT COUNT(*) FROM exam_practice_wrong_questions").fetchone()[0] == 0
    assert test_db.execute("SELECT COUNT(*) FROM exam_practice_drafts").fetchone()[0] == 0


def test_practice_finishes_unseen_questions_before_repeating_wrong_ones(test_db):
    result = replace_active_practice_sources_with_unified_question_bank(conn=test_db)
    bank_id = result["bank_id"]
    test_db.commit()
    questions = get_random_practice_questions(limit=30, user_id=17)
    assert len(questions) == 30
    assert {question["paper_id"] for question in questions} == {bank_id}

    all_questions = get_random_practice_questions(limit=220, user_id=98)
    assert len(all_questions) == 220
    assert any(
        [option["key"] for option in question["options"]] == ["A", "B", "C", "D", "E"]
        for question in all_questions
    )

    question_ids = [row[0] for row in test_db.execute(
        "SELECT id FROM exam_questions WHERE paper_id = ? ORDER BY id", (bank_id,)
    )]
    for question_id in question_ids:
        test_db.execute(
            "INSERT INTO exam_practice_attempts (user_id, question_id, answer_text, is_correct, accuracy_credit, created_at, practice_session_id) VALUES (17, ?, 'A', 1, 1, '2026-09-08 08:00:00', 'first-round')",
            (question_id,),
        )
    for question_id in question_ids[:2]:
        test_db.execute(
            "INSERT INTO exam_practice_wrong_questions (user_id, question_id, wrong_count, last_answer_text, first_wrong_at, last_wrong_at) VALUES (17, ?, 1, 'A', '2026-09-08 08:00:00', '2026-09-08 08:00:00')",
            (question_id,),
        )
    test_db.commit()

    retry = get_random_practice_questions(limit=30, user_id=17)
    assert {question["id"] for question in retry} == set(question_ids[:2])
