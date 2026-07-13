import sqlite3
import subprocess
import sys

from tools.regrade_practice_attempts import regrade_all_exam_scores, regrade_practice_attempts


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
            paper_id INTEGER,
            question_type TEXT NOT NULL,
            order_no INTEGER DEFAULT 0,
            correct_answer TEXT,
            keywords TEXT,
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


def build_exam_regrade_db():
    conn = build_practice_db()
    conn.executescript(
        """
        CREATE TABLE exam_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL DEFAULT 60,
            total_score INTEGER NOT NULL DEFAULT 100,
            source_type TEXT NOT NULL DEFAULT 'exam',
            create_time TEXT
        );
        CREATE TABLE exam_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            paper_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            objective_score REAL NOT NULL DEFAULT 0,
            suggested_subjective_score REAL NOT NULL DEFAULT 0,
            final_subjective_score REAL,
            final_score REAL,
            started_at TEXT,
            submitted_at TEXT
        );
        CREATE TABLE exam_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            answer_text TEXT NOT NULL DEFAULT '',
            auto_score REAL NOT NULL DEFAULT 0,
            suggested_score REAL NOT NULL DEFAULT 0,
            final_score REAL,
            UNIQUE (attempt_id, question_id)
        );
        """
    )
    conn.execute(
        """
        INSERT INTO exam_papers (
            title, duration_minutes, total_score, source_type, create_time
        ) VALUES ('Historical weighted paper', 50, 150, 'exam', '2026-07-13 00:00:00')
        """
    )
    conn.executemany(
        """
        INSERT INTO exam_questions (
            paper_id, question_type, correct_answer, score
        ) VALUES (1, ?, ?, ?)
        """,
        [
            ("true_false", "正确", 5),
            ("single_choice", "B", 5),
        ],
    )
    conn.execute(
        """
        INSERT INTO exam_attempts (
            user_id, paper_id, status, objective_score,
            suggested_subjective_score, final_score, started_at, submitted_at
        ) VALUES (1, 1, 'completed', 0, 0, 0, '2026-07-13 10:00:00', '2026-07-13 10:10:00')
        """
    )
    conn.executemany(
        """
        INSERT INTO exam_answers (
            attempt_id, question_id, answer_text, auto_score, suggested_score, final_score
        ) VALUES (1, ?, ?, ?, 0, ?)
        """,
        [
            (2, "√", 0, 0),
            (3, "A", 0, 0),
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


def test_regrade_all_exam_scores_updates_practice_formal_and_paper_totals():
    conn = build_exam_regrade_db()

    dry_run = regrade_all_exam_scores(conn, apply_changes=False)
    assert dry_run["formal"]["changed_attempts"] == 1
    assert dry_run["papers"]["changed_papers"] == 1

    applied = regrade_all_exam_scores(conn, apply_changes=True)

    assert applied["practice"]["changed_attempts"] == 3
    assert applied["formal"]["changed_answers"] == 1
    assert applied["formal"]["changed_attempts"] == 1
    assert applied["papers"]["changed_papers"] == 1
    assert conn.execute("SELECT total_score FROM exam_papers WHERE id = 1").fetchone()[0] == 100
    answer = conn.execute(
        "SELECT auto_score, final_score FROM exam_answers WHERE attempt_id = 1 AND question_id = 2"
    ).fetchone()
    attempt = conn.execute(
        "SELECT objective_score, final_score FROM exam_attempts WHERE id = 1"
    ).fetchone()
    assert answer["auto_score"] == 5
    assert answer["final_score"] == 5
    assert attempt["objective_score"] == 50
    assert attempt["final_score"] == 50


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
