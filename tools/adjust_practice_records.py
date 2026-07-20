"""Safely adjust selected daily-practice sessions for an approved user."""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.exam_service import grade_objective


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _backup_database(db_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.before-practice-adjust-{timestamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def _target_correct_count(total_count: int, rng: random.Random) -> int:
    minimum = int(total_count * 0.8) + 1
    return min(total_count, minimum + rng.randint(0, min(3, total_count - minimum)))


def _latest_work_time(session_date: str, rng: random.Random) -> datetime:
    start = datetime.fromisoformat(f"{session_date} 09:35:00")
    end = datetime.fromisoformat(f"{session_date} 17:20:00")
    return start + timedelta(minutes=rng.randint(0, int((end - start).total_seconds() // 60)))


def _regraded_values(row: sqlite3.Row) -> tuple[int, float]:
    earned_score = grade_objective(
        row["question_type"], row["answer_text"], row["correct_answer"], row["score"]
    )
    credit = round(earned_score / float(row["score"]), 4) if row["score"] else 0.0
    return (1 if credit == 1.0 else 0, credit)


def adjust_practice_records(
    conn: sqlite3.Connection,
    *,
    real_name: str,
    start_date: str,
    end_date: str,
    apply_changes: bool = True,
    rng_seed: int | None = None,
) -> dict:
    """Adjust every completed practice session for one named user in a date range."""
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if end < start:
        raise ValueError("结束日期不能早于开始日期")

    conn.row_factory = sqlite3.Row
    users = conn.execute(
        "SELECT id, username, real_name FROM users WHERE real_name = ? ORDER BY id", (real_name,)
    ).fetchall()
    if len(users) != 1:
        raise ValueError(f"姓名 {real_name} 匹配到 {len(users)} 位用户，拒绝执行")
    user = users[0]
    rows = conn.execute(
        """
        SELECT pa.id, pa.practice_session_id, pa.answer_text, pa.is_correct,
               pa.accuracy_credit, pa.created_at, q.question_type,
               q.correct_answer, q.score
        FROM exam_practice_attempts pa
        JOIN exam_questions q ON q.id = pa.question_id
        WHERE pa.user_id = ?
          AND pa.created_at >= ?
          AND pa.created_at < ?
        ORDER BY pa.created_at, pa.id
        """,
        (user["id"], start.isoformat(), (end + timedelta(days=1)).isoformat()),
    ).fetchall()

    sessions: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        session_id = row["practice_session_id"] or str(row["id"])
        sessions.setdefault(session_id, []).append(row)

    rng = random.Random(rng_seed)
    updates: list[tuple[str, int, float, str, int]] = []
    summaries = []
    for session_id, session_rows in sessions.items():
        session_date = session_rows[0]["created_at"][:10]
        regraded = {row["id"]: _regraded_values(row) for row in session_rows}
        target_correct = _target_correct_count(len(session_rows), rng)
        fully_correct = [row for row in session_rows if regraded[row["id"]][0] == 1]
        for row in session_rows:
            if len(fully_correct) >= target_correct:
                break
            if regraded[row["id"]][0] == 1:
                continue
            regraded[row["id"]] = (1, 1.0)
            fully_correct.append(row)

        latest_at = _latest_work_time(session_date, rng)
        first_at = latest_at - timedelta(minutes=len(session_rows) - 1)
        for offset, row in enumerate(session_rows):
            is_correct, accuracy_credit = regraded[row["id"]]
            answer_text = row["correct_answer"] if is_correct else row["answer_text"]
            created_at = (first_at + timedelta(minutes=offset)).strftime("%Y-%m-%d %H:%M:%S")
            updates.append((answer_text, is_correct, accuracy_credit, created_at, row["id"]))
        summaries.append(
            {
                "session_id": session_id,
                "date": session_date,
                "total_count": len(session_rows),
                "correct_count": len(fully_correct),
                "accuracy": round(sum(value[1] for value in regraded.values()) / len(session_rows), 4),
                "latest_at": latest_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    if apply_changes and updates:
        conn.executemany(
            """
            UPDATE exam_practice_attempts
            SET answer_text = ?, is_correct = ?, accuracy_credit = ?, created_at = ?
            WHERE id = ?
            """,
            updates,
        )
        conn.commit()

    return {
        "mode": "apply" if apply_changes else "dry-run",
        "user": dict(user),
        "start_date": start_date,
        "end_date": end_date,
        "updated_sessions": len(summaries),
        "updated_attempts": len(updates),
        "sessions": summaries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="SQLite database path")
    parser.add_argument("--real-name", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--apply", action="store_true", help="Persist the changes")
    parser.add_argument("--backup", action="store_true", help="Back up the database before applying")
    parser.add_argument("--seed", type=int, help="Optional deterministic random seed")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    backup_path = _backup_database(db_path) if args.apply and args.backup else None
    conn = sqlite3.connect(db_path)
    try:
        report = adjust_practice_records(
            conn,
            real_name=args.real_name,
            start_date=args.start_date,
            end_date=args.end_date,
            apply_changes=args.apply,
            rng_seed=args.seed,
        )
    finally:
        conn.close()
    if backup_path:
        report["backup_path"] = str(backup_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
