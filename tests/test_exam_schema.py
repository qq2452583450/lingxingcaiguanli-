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
        "exam_retroactive_checkins",
        "exam_monthly_checkin_reports",
        "exam_retake_eligibilities",
    }.issubset(names)


def test_exam_attempts_reference_existing_users(test_db):
    conn = sqlite3.connect(test_db)
    columns = {row[1]: row for row in conn.execute("PRAGMA table_info(exam_attempts)")}

    assert columns["user_id"][2].upper() == "INTEGER"
    assert columns["paper_id"][2].upper() == "INTEGER"
    assert columns["status"][2].upper() == "TEXT"
    assert columns["retake_eligibility_id"][2].upper() == "INTEGER"


def test_exam_practice_attempts_have_session_id(test_db):
    conn = sqlite3.connect(test_db)
    try:
        columns = {
            row[1]: row
            for row in conn.execute("PRAGMA table_info(exam_practice_attempts)")
        }
        indexes = [
            row[1]
            for row in conn.execute("PRAGMA index_list(exam_practice_attempts)")
        ]
    finally:
        conn.close()

    assert "practice_session_id" in columns
    assert "idx_exam_practice_session" in indexes


def test_exam_schema_upgrades_existing_practice_attempts_table():
    from database.exam_schema import init_exam_schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT)")
    conn.execute(
        """
        CREATE TABLE exam_practice_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            answer_text TEXT NOT NULL,
            is_correct INTEGER,
            created_at TEXT NOT NULL
        )
        """
    )

    init_exam_schema(conn)

    columns = {
        row[1]: row
        for row in conn.execute("PRAGMA table_info(exam_practice_attempts)")
    }
    indexes = [
        row[1]
        for row in conn.execute("PRAGMA index_list(exam_practice_attempts)")
    ]

    assert "practice_session_id" in columns
    assert "idx_exam_practice_session" in indexes


def test_exam_schema_clears_legacy_auto_current_paper_once():
    from database.exam_schema import init_exam_schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT)")
    conn.execute(
        """
        CREATE TABLE exam_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO exam_settings (key, value) VALUES (?, ?)",
        ("current_exam_paper_id", "1"),
    )

    init_exam_schema(conn)

    assert conn.execute(
        "SELECT value FROM exam_settings WHERE key = ?",
        ("current_exam_paper_id",),
    ).fetchone() is None
    assert conn.execute(
        "SELECT value FROM exam_settings WHERE key = ?",
        ("manual_current_exam_required_migration_20260711",),
    ).fetchone()[0] == "done"

    conn.execute(
        "INSERT INTO exam_settings (key, value) VALUES (?, ?)",
        ("current_exam_paper_id", "2"),
    )
    init_exam_schema(conn)

    assert conn.execute(
        "SELECT value FROM exam_settings WHERE key = ?",
        ("current_exam_paper_id",),
    ).fetchone()[0] == "2"


def test_exam_schema_preserves_caller_transaction_rollback():
    from database.exam_schema import init_exam_schema

    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT
        )
        """
    )
    conn.commit()

    conn.execute("BEGIN")
    conn.execute("CREATE TABLE rollback_marker (id INTEGER PRIMARY KEY)")
    init_exam_schema(conn)
    conn.rollback()

    names = table_names(conn)
    assert "rollback_marker" not in names
    assert "exam_papers" not in names
