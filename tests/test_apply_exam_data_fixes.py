import sqlite3

from tools.apply_exam_data_fixes import apply_fix, ensure_data_fix_table


def build_data_fix_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            real_name TEXT
        );
        CREATE TABLE exam_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            source_type TEXT NOT NULL
        );
        CREATE TABLE exam_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER NOT NULL,
            question_type TEXT NOT NULL,
            order_no INTEGER NOT NULL,
            correct_answer TEXT
        );
        CREATE TABLE exam_practice_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            answer_text TEXT NOT NULL,
            is_correct INTEGER,
            accuracy_credit REAL DEFAULT 0,
            created_at TEXT NOT NULL,
            practice_session_id TEXT
        );
        CREATE TABLE exam_practice_wrong_questions (
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            wrong_count INTEGER NOT NULL DEFAULT 1,
            last_answer_text TEXT NOT NULL DEFAULT '',
            first_wrong_at TEXT,
            last_wrong_at TEXT,
            PRIMARY KEY (user_id, question_id)
        );
        """
    )
    conn.execute(
        "INSERT INTO users (username, real_name) VALUES (?, ?)",
        ("liuguanghua", "刘光华"),
    )
    conn.execute(
        "INSERT INTO exam_papers (title, source_type) VALUES (?, ?)",
        ("正式卷", "exam"),
    )
    conn.executemany(
        """
        INSERT INTO exam_questions (
            paper_id, question_type, order_no, correct_answer
        ) VALUES (1, ?, ?, ?)
        """,
        [("true_false", index, "正确" if index % 2 else "错误") for index in range(1, 31)],
    )
    conn.commit()
    return conn


def test_daily_practice_data_fix_sets_liuguanghua_to_thirty_questions_at_displayed_87_percent():
    conn = build_data_fix_db()
    ensure_data_fix_table(conn)
    fix = {
        "id": "2026-07-13-liuguanghua-daily-practice",
        "type": "daily_practice_status",
        "user": "liuguanghua",
        "date": "2026-07-13",
        "answered_count": 30,
        "display_accuracy_percent": 87,
    }

    result = apply_fix(conn, fix, apply_changes=True)
    skipped = apply_fix(conn, fix, apply_changes=True)
    row = conn.execute(
        """
        SELECT COUNT(*) AS total_count,
               SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_count,
               SUM(accuracy_credit) AS accuracy_credit
        FROM exam_practice_attempts
        WHERE user_id = 1
          AND created_at LIKE '2026-07-13%'
        """
    ).fetchone()

    assert result["status"] == "applied"
    assert result["result"]["answered_count"] == 30
    assert result["result"]["correct_count"] == 26
    assert result["result"]["display_accuracy_percent"] == 87
    assert skipped["status"] == "skipped"
    assert row["total_count"] == 30
    assert row["correct_count"] == 26
    assert round(row["accuracy_credit"] / row["total_count"] * 100) == 87
    assert conn.execute("SELECT COUNT(*) FROM exam_practice_wrong_questions").fetchone()[0] == 4
