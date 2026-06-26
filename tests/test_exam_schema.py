import sqlite3


def table_names(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def test_exam_schema_creates_required_tables(test_db):
    conn = sqlite3.connect(test_db)
    names = table_names(conn)

    assert {
        "exam_papers",
        "exam_questions",
        "exam_question_options",
        "exam_attempts",
        "exam_answers",
        "exam_subjective_reviews",
        "exam_practice_attempts",
        "exam_settings",
    }.issubset(names)


def test_exam_attempts_reference_existing_users(test_db):
    conn = sqlite3.connect(test_db)
    columns = {row[1]: row for row in conn.execute("PRAGMA table_info(exam_attempts)")}

    assert columns["user_id"][2].upper() == "INTEGER"
    assert columns["paper_id"][2].upper() == "INTEGER"
    assert columns["status"][2].upper() == "TEXT"
