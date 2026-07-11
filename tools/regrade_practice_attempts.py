"""Regrade saved daily-practice attempts with the current objective rules."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.exam_service import grade_objective


DEFAULT_DB_NAME = "零星材管理系统.db"


def _row_value(row, key, default=None):
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def _needs_update(old_correct, old_credit, new_correct: int, new_credit: float) -> bool:
    current_correct = 1 if old_correct == 1 else 0
    current_credit = float(old_credit or 0)
    return current_correct != new_correct or abs(current_credit - new_credit) > 0.0001


def _session_summary(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT u.id AS user_id,
               u.username,
               u.real_name,
               COALESCE(pa.practice_session_id, CAST(pa.id AS TEXT)) AS session_id,
               COUNT(*) AS total_count,
               SUM(CASE WHEN pa.is_correct = 1 THEN 1 ELSE 0 END) AS correct_count,
               SUM(COALESCE(pa.accuracy_credit, CASE WHEN pa.is_correct = 1 THEN 1 ELSE 0 END)) AS accuracy_credit,
               MIN(pa.created_at) AS started_at,
               MAX(pa.created_at) AS latest_at
        FROM exam_practice_attempts pa
        JOIN users u ON u.id = pa.user_id
        GROUP BY u.id, u.username, u.real_name, COALESCE(pa.practice_session_id, CAST(pa.id AS TEXT))
        ORDER BY latest_at DESC, u.id
        """
    ).fetchall()
    sessions = []
    for row in rows:
        total_count = int(row["total_count"] or 0)
        accuracy_credit = float(row["accuracy_credit"] or 0)
        sessions.append(
            {
                "user_id": row["user_id"],
                "username": row["username"],
                "real_name": row["real_name"],
                "session_id": row["session_id"],
                "total_count": total_count,
                "correct_count": int(row["correct_count"] or 0),
                "accuracy": round(accuracy_credit / total_count, 4) if total_count else 0.0,
                "started_at": row["started_at"],
                "latest_at": row["latest_at"],
            }
        )
    return sessions


def regrade_practice_attempts(conn: sqlite3.Connection, apply_changes: bool = False) -> dict:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT pa.id,
               pa.user_id,
               pa.question_id,
               pa.answer_text,
               pa.is_correct,
               pa.accuracy_credit,
               q.question_type,
               q.correct_answer,
               q.score,
               u.username,
               u.real_name
        FROM exam_practice_attempts pa
        JOIN exam_questions q ON q.id = pa.question_id
        JOIN users u ON u.id = pa.user_id
        ORDER BY pa.id
        """
    ).fetchall()

    updates = []
    users_with_practice = {
        row["user_id"]: {
            "user_id": row["user_id"],
            "username": row["username"],
            "real_name": row["real_name"],
        }
        for row in rows
    }
    for row in rows:
        earned_score = grade_objective(
            row["question_type"],
            row["answer_text"],
            row["correct_answer"],
            row["score"],
        )
        new_correct = 1 if earned_score == float(row["score"]) else 0
        new_credit = round(earned_score / float(row["score"]), 4) if row["score"] else 0.0
        if _needs_update(row["is_correct"], row["accuracy_credit"], new_correct, new_credit):
            updates.append(
                {
                    "attempt_id": row["id"],
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "real_name": row["real_name"],
                    "old_is_correct": 1 if row["is_correct"] == 1 else 0,
                    "new_is_correct": new_correct,
                    "old_accuracy_credit": round(float(row["accuracy_credit"] or 0), 4),
                    "new_accuracy_credit": new_credit,
                }
            )

    if apply_changes:
        conn.executemany(
            """
            UPDATE exam_practice_attempts
            SET is_correct = ?, accuracy_credit = ?
            WHERE id = ?
            """,
            [
                (update["new_is_correct"], update["new_accuracy_credit"], update["attempt_id"])
                for update in updates
            ],
        )
        conn.commit()

    return {
        "mode": "apply" if apply_changes else "dry-run",
        "total_attempts": len(rows),
        "practice_users": len(users_with_practice),
        "changed_attempts": len(updates),
        "affected_users": len({update["user_id"] for update in updates}),
        "users": list(users_with_practice.values()),
        "updates": updates,
        "sessions": _session_summary(conn) if apply_changes else [],
    }


def backup_database(db_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.before-practice-regrade-{timestamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB_NAME, help="SQLite database path.")
    parser.add_argument("--apply", action="store_true", help="Persist recalculated scores.")
    parser.add_argument("--backup", action="store_true", help="Copy the database before applying changes.")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    backup_path = None
    if args.apply and args.backup:
        backup_path = backup_database(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        report = regrade_practice_attempts(conn, apply_changes=args.apply)
    finally:
        conn.close()

    if backup_path:
        report["backup_path"] = str(backup_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
