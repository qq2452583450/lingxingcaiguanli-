import sqlite3

import pytest

from tools.release_stale_formal_attempts import FIX_ID, release_stale_attempts


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE exam_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE exam_papers (id INTEGER PRIMARY KEY, title TEXT, source_type TEXT);
        CREATE TABLE exam_attempts (
            id INTEGER PRIMARY KEY, user_id INTEGER, paper_id INTEGER, status TEXT,
            started_at TEXT, retake_eligibility_id INTEGER
        );
        CREATE TABLE exam_answers (id INTEGER PRIMARY KEY, attempt_id INTEGER);
        CREATE TABLE exam_subjective_reviews (id INTEGER PRIMARY KEY, answer_id INTEGER);
        CREATE TABLE exam_retake_eligibilities (
            id INTEGER PRIMARY KEY, source_attempt_id INTEGER, used_attempt_id INTEGER,
            status TEXT, used_at TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO exam_papers (id, title, source_type) VALUES (?, ?, 'exam')",
        [(1, "综合题库一（满分 100 分）"), (4, "综合题库四（满分 100 分）")],
    )
    conn.execute("INSERT INTO exam_settings (key, value) VALUES ('current_exam_paper_id', '4')")
    conn.executemany(
        "INSERT INTO exam_attempts VALUES (?, ?, ?, ?, ?, ?)",
        [
            (11, 101, 1, "in_progress", "2026-09-04 09:00:00", None),
            (12, 102, 1, "completed", "2026-09-04 10:00:00", None),
            (13, 103, 1, "in_progress", "2026-09-04 11:00:00", 7),
            (14, 104, 4, "in_progress", "2026-09-05 09:00:00", None),
        ],
    )
    conn.execute("INSERT INTO exam_answers VALUES (21, 11)")
    conn.execute("INSERT INTO exam_subjective_reviews VALUES (31, 21)")
    conn.commit()
    yield conn
    conn.close()


def test_releases_only_non_retake_stale_in_progress_attempts(db):
    result = release_stale_attempts(db, "综合题库四", apply_changes=True)
    db.commit()

    assert result["status"] == "applied"
    assert [row["id"] for row in result["released_attempts"]] == [11]
    assert [row["id"] for row in db.execute("SELECT id FROM exam_attempts ORDER BY id")] == [12, 13, 14]
    assert db.execute("SELECT * FROM exam_answers").fetchall() == []
    assert db.execute("SELECT * FROM exam_subjective_reviews").fetchall() == []
    assert db.execute("SELECT id FROM data_fix_runs WHERE id = ?", (FIX_ID,)).fetchone()
    assert release_stale_attempts(db, "综合题库四", apply_changes=True)["status"] == "skipped"


def test_refuses_to_release_attempts_if_current_paper_changed(db):
    with pytest.raises(ValueError, match="does not match"):
        release_stale_attempts(db, "综合题库三", apply_changes=True)
