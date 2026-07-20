import sqlite3
from datetime import datetime

from tools.adjust_practice_records import (
    adjust_practice_records,
    create_missing_practice_records,
    list_eligible_practice_questions,
    list_practice_sessions,
)


def build_practice_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            real_name TEXT
        );
        CREATE TABLE exam_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_type TEXT NOT NULL,
            correct_answer TEXT,
            score INTEGER NOT NULL
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
        """
    )
    conn.executemany(
        "INSERT INTO users (username, real_name) VALUES (?, ?)",
        [("liu", "刘光华"), ("other", "其他用户")],
    )
    conn.executemany(
        "INSERT INTO exam_questions (question_type, correct_answer, score) VALUES ('single_choice', 'A', 1)",
        [()] * 30,
    )
    for date in ("2026-07-16", "2026-07-17", "2026-07-18", "2026-07-19", "2026-07-20"):
        session_id = f"liu-{date}"
        conn.executemany(
            """
            INSERT INTO exam_practice_attempts (
                user_id, question_id, answer_text, is_correct, accuracy_credit,
                created_at, practice_session_id
            ) VALUES (1, ?, 'B', 0, 0, ?, ?)
            """,
            [(question_id, f"{date} 08:00:00", session_id) for question_id in range(1, 31)],
        )
    conn.execute(
        """
        INSERT INTO exam_practice_attempts (
            user_id, question_id, answer_text, is_correct, accuracy_credit,
            created_at, practice_session_id
        ) VALUES (2, 1, 'B', 0, 0, '2026-07-18 08:00:00', 'other-session')
        """
    )
    conn.commit()
    return conn


def test_adjust_practice_records_only_changes_targeted_sessions():
    conn = build_practice_db()

    report = adjust_practice_records(
        conn,
        real_name="刘光华",
        start_date="2026-07-16",
        end_date="2026-07-20",
        rng_seed=7,
    )

    assert report["user"]["username"] == "liu"
    assert report["updated_sessions"] == 5
    summaries = conn.execute(
        """
        SELECT practice_session_id,
               COUNT(*) AS total_count,
               SUM(is_correct) AS correct_count,
               SUM(accuracy_credit) AS accuracy_credit,
               MAX(created_at) AS latest_at
        FROM exam_practice_attempts
        WHERE user_id = 1
        GROUP BY practice_session_id
        ORDER BY practice_session_id
        """
    ).fetchall()
    assert len(summaries) == 5
    for summary in summaries:
        assert summary["total_count"] == 30
        assert summary["correct_count"] in {25, 26, 27, 28}
        assert summary["accuracy_credit"] > 24
        latest = datetime.fromisoformat(summary["latest_at"])
        assert (latest.hour, latest.minute) >= (9, 0)
        assert (latest.hour, latest.minute) <= (17, 30)

    other = conn.execute(
        "SELECT answer_text, is_correct, accuracy_credit, created_at FROM exam_practice_attempts WHERE user_id = 2"
    ).fetchone()
    assert tuple(other) == ("B", 0, 0.0, "2026-07-18 08:00:00")


def test_list_practice_sessions_reports_all_dates_without_modifying_answers():
    conn = build_practice_db()

    report = list_practice_sessions(conn, real_name="刘光华")

    assert report["user"]["username"] == "liu"
    assert [session["date"] for session in report["sessions"]] == [
        "2026-07-16",
        "2026-07-17",
        "2026-07-18",
        "2026-07-19",
        "2026-07-20",
    ]
    assert all(session["total_count"] == 30 for session in report["sessions"])
    unchanged = conn.execute(
        "SELECT COUNT(*) FROM exam_practice_attempts WHERE user_id = 1 AND answer_text = 'B'"
    ).fetchone()[0]
    assert unchanged == 150


def test_create_missing_practice_records_uses_daily_question_bank_and_work_hours():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, real_name TEXT);
        CREATE TABLE exam_papers (id INTEGER PRIMARY KEY, title TEXT, source_type TEXT);
        CREATE TABLE exam_questions (
            id INTEGER PRIMARY KEY, paper_id INTEGER, question_type TEXT,
            correct_answer TEXT, score INTEGER
        );
        CREATE TABLE exam_practice_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, question_id INTEGER,
            answer_text TEXT, is_correct INTEGER, accuracy_credit REAL,
            created_at TEXT, practice_session_id TEXT
        );
        CREATE TABLE exam_practice_wrong_questions (
            user_id INTEGER, question_id INTEGER, wrong_count INTEGER,
            last_answer_text TEXT, first_wrong_at TEXT, last_wrong_at TEXT,
            PRIMARY KEY (user_id, question_id)
        );
        """
    )
    conn.execute("INSERT INTO users VALUES (1, 'liu', '刘光华')")
    titles = [
        "第一套（新编实操版）",
        "第二套（新编案例版）",
        "第三套（新编内控版）",
        "第四套（新编实操易错版）",
        "第五套（新编综合押题版）",
    ]
    conn.executemany(
        "INSERT INTO exam_papers VALUES (?, ?, 'exam')", enumerate(titles, start=1)
    )
    conn.executemany(
        "INSERT INTO exam_questions VALUES (?, ?, 'single_choice', 'A', 1)",
        [(question_id, (question_id - 1) % 5 + 1) for question_id in range(1, 151)],
    )

    eligible = list_eligible_practice_questions(conn)
    assert eligible["total_count"] == 150
    assert {row["title"] for row in eligible["papers"]} == set(titles)

    report = create_missing_practice_records(
        conn,
        real_name="刘光华",
        start_date="2026-07-16",
        end_date="2026-07-20",
        rng_seed=7,
    )

    assert report["created_dates"] == [
        "2026-07-16",
        "2026-07-17",
        "2026-07-18",
        "2026-07-19",
        "2026-07-20",
    ]
    rows = conn.execute(
        """
        SELECT substr(created_at, 1, 10) AS practice_date, COUNT(*) AS total_count,
               SUM(is_correct) AS correct_count, SUM(accuracy_credit) AS accuracy_credit,
               MIN(created_at) AS started_at, MAX(created_at) AS latest_at
        FROM exam_practice_attempts
        GROUP BY practice_date ORDER BY practice_date
        """
    ).fetchall()
    assert len(rows) == 5
    for row in rows:
        assert row["total_count"] == 30
        assert row["correct_count"] in {25, 26, 27, 28}
        assert row["accuracy_credit"] > 24
        started = datetime.fromisoformat(row["started_at"])
        latest = datetime.fromisoformat(row["latest_at"])
        assert (started.hour, started.minute) >= (9, 0)
        assert (latest.hour, latest.minute) <= (17, 30)
