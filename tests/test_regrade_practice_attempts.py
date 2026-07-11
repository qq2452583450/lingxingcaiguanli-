import sqlite3
import subprocess
import sys

from tools.regrade_practice_attempts import regrade_practice_attempts


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
        [
            ("u1", "User One"),
            ("u2", "User Two"),
            ("u3", "User Three"),
        ],
    )
    conn.execute(
        "INSERT INTO exam_questions (question_type, correct_answer, score) VALUES (?, ?, ?)",
        ("multiple_choice", "ABC", 3),
    )
    conn.executemany(
        """
        INSERT INTO exam_practice_attempts (
            user_id, question_id, answer_text, is_correct, accuracy_credit,
            created_at, practice_session_id
        ) VALUES (?, 1, ?, ?, ?, '2026-07-11 10:00:00', ?)
        """,
        [
            (1, "AB", 0, 0.0, "s1"),
            (2, "ABC", 0, 0.0, "s2"),
            (3, "ABD", 1, 1.0, "s3"),
        ],
    )
    conn.commit()
    return conn


def test_regrade_practice_attempts_applies_current_multiple_choice_rule():
    conn = build_practice_db()

    dry_run = regrade_practice_attempts(conn, apply_changes=False)
    assert dry_run["changed_attempts"] == 3
    assert dry_run["affected_users"] == 3
    assert conn.execute(
        "SELECT accuracy_credit FROM exam_practice_attempts WHERE user_id = 1"
    ).fetchone()[0] == 0.0

    applied = regrade_practice_attempts(conn, apply_changes=True)

    assert applied["changed_attempts"] == 3
    assert applied["affected_users"] == 3
    rows = conn.execute(
        """
        SELECT user_id, is_correct, ROUND(accuracy_credit, 4) AS accuracy_credit
        FROM exam_practice_attempts
        ORDER BY user_id
        """
    ).fetchall()
    assert [dict(row) for row in rows] == [
        {"user_id": 1, "is_correct": 0, "accuracy_credit": 0.6667},
        {"user_id": 2, "is_correct": 1, "accuracy_credit": 1.0},
        {"user_id": 3, "is_correct": 0, "accuracy_credit": 0.0},
    ]


def test_regrade_script_runs_as_standalone_cli(tmp_path):
    db_path = tmp_path / "practice.db"
    source = build_practice_db()
    backup = sqlite3.connect(db_path)
    source.backup(backup)
    backup.close()
    source.close()

    result = subprocess.run(
        [sys.executable, "tools/regrade_practice_attempts.py", "--db", str(db_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert '"practice_users": 3' in result.stdout
