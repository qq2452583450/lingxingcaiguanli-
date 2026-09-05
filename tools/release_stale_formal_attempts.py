"""Release obsolete in-progress formal exam attempts after a paper switch."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


FIX_ID = "2026-09-05-release-stale-formal-attempts"


def _ensure_fix_runs(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS data_fix_runs (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _current_paper(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT p.id, p.title
        FROM exam_settings s
        JOIN exam_papers p ON p.id = CAST(s.value AS INTEGER)
        WHERE s.key = 'current_exam_paper_id' AND p.source_type = 'exam'
        """
    ).fetchone()
    if not row:
        raise ValueError("No current formal exam paper is configured")
    return row


def _stale_attempts(conn: sqlite3.Connection, current_paper_id: int) -> list[sqlite3.Row]:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(exam_attempts)")}
    retake_filter = "AND att.retake_eligibility_id IS NULL" if "retake_eligibility_id" in columns else ""
    return conn.execute(
        f"""
        SELECT att.id, att.user_id, att.paper_id, p.title AS paper_title, att.started_at
        FROM exam_attempts att
        JOIN exam_papers p ON p.id = att.paper_id
        WHERE att.status = 'in_progress'
          AND att.paper_id <> ?
          {retake_filter}
        ORDER BY att.id
        """,
        (current_paper_id,),
    ).fetchall()


def _delete_attempts(conn: sqlite3.Connection, attempt_ids: list[int]) -> None:
    if not attempt_ids:
        return
    marks = ",".join("?" for _ in attempt_ids)
    conn.execute(
        f"""
        UPDATE exam_retake_eligibilities
        SET status = 'open', used_attempt_id = NULL, used_at = NULL
        WHERE used_attempt_id IN ({marks})
        """,
        attempt_ids,
    )
    conn.execute(
        f"""
        UPDATE exam_retake_eligibilities
        SET source_attempt_id = NULL
        WHERE source_attempt_id IN ({marks}) AND used_attempt_id IS NOT NULL
        """,
        attempt_ids,
    )
    conn.execute(
        f"""
        DELETE FROM exam_retake_eligibilities
        WHERE source_attempt_id IN ({marks}) AND used_attempt_id IS NULL
        """,
        attempt_ids,
    )
    conn.execute(
        f"""
        DELETE FROM exam_subjective_reviews
        WHERE answer_id IN (
            SELECT id FROM exam_answers WHERE attempt_id IN ({marks})
        )
        """,
        attempt_ids,
    )
    conn.execute(f"DELETE FROM exam_answers WHERE attempt_id IN ({marks})", attempt_ids)
    conn.execute(f"DELETE FROM exam_attempts WHERE id IN ({marks})", attempt_ids)


def release_stale_attempts(
    conn: sqlite3.Connection,
    expected_title: str,
    apply_changes: bool,
) -> dict:
    _ensure_fix_runs(conn)
    if conn.execute("SELECT 1 FROM data_fix_runs WHERE id = ?", (FIX_ID,)).fetchone():
        return {"status": "skipped", "fix_id": FIX_ID}

    current_paper = _current_paper(conn)
    if expected_title not in str(current_paper["title"]):
        raise ValueError(f"Current paper does not match expected title: {current_paper['title']}")
    stale_attempts = _stale_attempts(conn, int(current_paper["id"]))
    result = {
        "status": "applied" if apply_changes else "dry-run",
        "fix_id": FIX_ID,
        "current_paper": dict(current_paper),
        "released_attempts": [dict(row) for row in stale_attempts],
    }
    if not apply_changes:
        return result

    _delete_attempts(conn, [int(row["id"]) for row in stale_attempts])
    conn.execute(
        "INSERT INTO data_fix_runs (id, applied_at) VALUES (?, ?)",
        (FIX_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="SQLite database path")
    parser.add_argument("--expected-title", default="综合题库四", help="Expected current paper title fragment")
    parser.add_argument("--apply", action="store_true", help="Persist the repair")
    parser.add_argument("--backup", action="store_true", help="Back up the database before applying")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    if args.backup and args.apply:
        backup_path = db_path.with_name(
            f"{db_path.stem}.before-{FIX_ID}-{datetime.now():%Y%m%d-%H%M%S}{db_path.suffix}"
        )
        shutil.copy2(db_path, backup_path)
        print(json.dumps({"backup": str(backup_path)}, ensure_ascii=False))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        result = release_stale_attempts(conn, args.expected_title, args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
