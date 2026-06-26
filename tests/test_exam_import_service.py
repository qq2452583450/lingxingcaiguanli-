from pathlib import Path

from services.exam_import_service import parse_exam_docx, import_exam_papers_from_docx
from services.exam_service import list_papers, get_paper_questions, get_current_exam_paper


def source_docx():
    return next(Path("docs/exam_sources").glob("*\u6750\u6599\u8fdb\u573a\u9a8c\u6536\u6807\u51c6\u4e13\u9879\u8003\u8bd5\u5377*.docx"))


def test_parse_receiving_exam_docx_has_five_complete_papers():
    papers = parse_exam_docx(source_docx())

    assert [paper["title"] for paper in papers] == [
        "\u7b2c\u4e00\u5957\uff08\u65b0\u7f16\u5b9e\u64cd\u7248\uff09",
        "\u7b2c\u4e8c\u5957\uff08\u65b0\u7f16\u6848\u4f8b\u7248\uff09",
        "\u7b2c\u4e09\u5957\uff08\u65b0\u7f16\u5185\u63a7\u7248\uff09",
        "\u7b2c\u56db\u5957\uff08\u65b0\u7f16\u5b9e\u64cd\u6613\u9519\u7248\uff09",
        "\u7b2c\u4e94\u5957\uff08\u65b0\u7f16\u7efc\u5408\u62bc\u9898\u7248\uff09",
    ]
    assert all(len(paper["questions"]) == 38 for paper in papers)


def test_import_exam_papers_sets_current_exam_paper(test_db):
    result = import_exam_papers_from_docx(source_docx())

    papers = list_papers()
    current = get_current_exam_paper()

    assert result == {"inserted": 5, "removed": 0}
    assert len(papers) == 5
    assert current["title"] == "\u7b2c\u4e00\u5957\uff08\u65b0\u7f16\u5b9e\u64cd\u7248\uff09"
    assert len(get_paper_questions(current["id"])) == 38


def test_reimport_removes_old_formal_exam_lifecycle_rows(test_db):
    first_result = import_exam_papers_from_docx(source_docx())
    old_current = get_current_exam_paper()
    old_question = get_paper_questions(old_current["id"])[0]

    cursor = test_db.cursor()
    cursor.execute(
        """
        INSERT INTO users (username, password, real_name, create_time)
        VALUES (?, ?, ?, ?)
        """,
        ("exam_user", "password", "Exam User", "2026-06-26 00:00:00"),
    )
    user_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO exam_attempts (
            user_id, paper_id, status, started_at
        ) VALUES (?, ?, ?, ?)
        """,
        (user_id, old_current["id"], "completed", "2026-06-26 00:00:00"),
    )
    attempt_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO exam_answers (
            attempt_id, question_id, answer_text, auto_score
        ) VALUES (?, ?, ?, ?)
        """,
        (attempt_id, old_question["id"], "A", 0),
    )
    answer_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO exam_subjective_reviews (
            answer_id, reviewer_id, suggested_score, final_score, reviewed_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (answer_id, user_id, 0, 0, "2026-06-26 00:00:00"),
    )
    review_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO exam_practice_attempts (
            user_id, question_id, answer_text, is_correct, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, old_question["id"], "A", 1, "2026-06-26 00:00:00"),
    )
    practice_id = cursor.lastrowid
    test_db.commit()

    second_result = import_exam_papers_from_docx(source_docx())
    papers = list_papers()
    current = get_current_exam_paper()

    assert first_result == {"inserted": 5, "removed": 0}
    assert second_result == {"inserted": 5, "removed": 5}
    assert len([paper for paper in papers if paper["source_type"] == "exam"]) == 5
    assert current["title"] == "\u7b2c\u4e00\u5957\uff08\u65b0\u7f16\u5b9e\u64cd\u7248\uff09"
    assert current["id"] != old_current["id"]
    assert test_db.execute(
        "SELECT COUNT(*) FROM exam_attempts WHERE id = ?",
        (attempt_id,),
    ).fetchone()[0] == 0
    assert test_db.execute(
        "SELECT COUNT(*) FROM exam_answers WHERE id = ?",
        (answer_id,),
    ).fetchone()[0] == 0
    assert test_db.execute(
        "SELECT COUNT(*) FROM exam_subjective_reviews WHERE id = ?",
        (review_id,),
    ).fetchone()[0] == 0
    assert test_db.execute(
        "SELECT COUNT(*) FROM exam_practice_attempts WHERE id = ?",
        (practice_id,),
    ).fetchone()[0] == 0
