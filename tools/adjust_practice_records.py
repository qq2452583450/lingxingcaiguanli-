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
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.exam_service import DAILY_PRACTICE_PAPER_TITLES, grade_objective


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


def list_practice_sessions(conn: sqlite3.Connection, *, real_name: str) -> dict:
    """Return all saved daily-practice sessions for one exact user name."""
    conn.row_factory = sqlite3.Row
    users = conn.execute(
        "SELECT id, username, real_name FROM users WHERE real_name = ? ORDER BY id", (real_name,)
    ).fetchall()
    if len(users) != 1:
        raise ValueError(f"姓名 {real_name} 匹配到 {len(users)} 位用户，拒绝执行")
    user = users[0]
    rows = conn.execute(
        """
        SELECT COALESCE(practice_session_id, CAST(id AS TEXT)) AS session_id,
               COUNT(*) AS total_count,
               SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_count,
               SUM(COALESCE(accuracy_credit, CASE WHEN is_correct = 1 THEN 1 ELSE 0 END)) AS accuracy_credit,
               MIN(created_at) AS started_at,
               MAX(created_at) AS latest_at
        FROM exam_practice_attempts
        WHERE user_id = ?
        GROUP BY COALESCE(practice_session_id, CAST(id AS TEXT))
        ORDER BY started_at, session_id
        """,
        (user["id"],),
    ).fetchall()
    sessions = []
    for row in rows:
        total_count = int(row["total_count"] or 0)
        accuracy_credit = float(row["accuracy_credit"] or 0)
        sessions.append(
            {
                "session_id": row["session_id"],
                "date": row["started_at"][:10],
                "total_count": total_count,
                "correct_count": int(row["correct_count"] or 0),
                "accuracy": round(accuracy_credit / total_count, 4) if total_count else 0.0,
                "started_at": row["started_at"],
                "latest_at": row["latest_at"],
            }
        )
    return {"user": dict(user), "sessions": sessions}


def create_missing_practice_records(
    conn: sqlite3.Connection,
    *,
    real_name: str,
    start_date: str,
    end_date: str,
    apply_changes: bool = True,
    rng_seed: int | None = None,
) -> dict:
    """Create one passing 30-question practice session for each missing day."""
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
    paper_titles = sorted(DAILY_PRACTICE_PAPER_TITLES)
    title_placeholders = ",".join("?" for _ in paper_titles)
    questions = conn.execute(
        f"""
        SELECT q.id, q.correct_answer
        FROM exam_questions q
        JOIN exam_papers p ON p.id = q.paper_id
        WHERE p.source_type = 'exam'
          AND p.title IN ({title_placeholders})
          AND q.question_type IN ('single_choice', 'multiple_choice', 'true_false')
        ORDER BY q.id
        """,
        paper_titles,
    ).fetchall()
    if len(questions) < 30:
        raise ValueError("打卡题库不足 30 道客观题，拒绝补建记录")

    rng = random.Random(rng_seed)
    created_dates = []
    skipped_dates = []
    sessions = []
    day = start
    while day <= end:
        day_text = day.isoformat()
        existing = conn.execute(
            """
            SELECT 1 FROM exam_practice_attempts
            WHERE user_id = ? AND created_at >= ? AND created_at < ?
            LIMIT 1
            """,
            (user["id"], day_text, (day + timedelta(days=1)).isoformat()),
        ).fetchone()
        if existing:
            skipped_dates.append(day_text)
            day += timedelta(days=1)
            continue

        selected_questions = rng.sample(questions, 30)
        correct_count = _target_correct_count(30, rng)
        correct_ids = {row["id"] for row in selected_questions[:correct_count]}
        latest_at = _latest_work_time(day_text, rng)
        first_at = latest_at - timedelta(minutes=29)
        session_id = f"manual-{day_text}-{user['username']}-daily-practice-{uuid4().hex[:8]}"
        for offset, question in enumerate(selected_questions):
            is_correct = question["id"] in correct_ids
            answer_text = question["correct_answer"] if is_correct else ""
            created_at = (first_at + timedelta(minutes=offset)).strftime("%Y-%m-%d %H:%M:%S")
            if apply_changes:
                conn.execute(
                    """
                    INSERT INTO exam_practice_attempts (
                        user_id, question_id, answer_text, is_correct,
                        accuracy_credit, created_at, practice_session_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user["id"], question["id"], answer_text, 1 if is_correct else 0,
                        1.0 if is_correct else 0.0, created_at, session_id,
                    ),
                )
                if is_correct:
                    conn.execute(
                        "DELETE FROM exam_practice_wrong_questions WHERE user_id = ? AND question_id = ?",
                        (user["id"], question["id"]),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO exam_practice_wrong_questions (
                            user_id, question_id, wrong_count, last_answer_text,
                            first_wrong_at, last_wrong_at
                        ) VALUES (?, ?, 1, ?, ?, ?)
                        ON CONFLICT(user_id, question_id) DO UPDATE SET
                            wrong_count = exam_practice_wrong_questions.wrong_count + 1,
                            last_answer_text = excluded.last_answer_text,
                            last_wrong_at = excluded.last_wrong_at
                        """,
                        (user["id"], question["id"], answer_text, created_at, created_at),
                    )
        created_dates.append(day_text)
        sessions.append(
            {
                "session_id": session_id,
                "date": day_text,
                "total_count": 30,
                "correct_count": correct_count,
                "accuracy": round(correct_count / 30, 4),
                "latest_at": latest_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        day += timedelta(days=1)

    if apply_changes:
        conn.commit()
    return {
        "mode": "apply" if apply_changes else "dry-run",
        "user": dict(user),
        "created_dates": created_dates,
        "skipped_dates": skipped_dates,
        "sessions": sessions,
    }


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
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--list-sessions", action="store_true", help="List sessions without changing data")
    parser.add_argument("--create-missing", action="store_true", help="Create one passing session for each missing day")
    parser.add_argument("--apply", action="store_true", help="Persist the changes")
    parser.add_argument("--backup", action="store_true", help="Back up the database before applying")
    parser.add_argument("--seed", type=int, help="Optional deterministic random seed")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    if args.list_sessions and args.create_missing:
        parser.error("--list-sessions and --create-missing cannot be used together")
    conn = sqlite3.connect(db_path)
    try:
        if args.list_sessions:
            report = list_practice_sessions(conn, real_name=args.real_name)
            backup_path = None
        else:
            if not args.start_date or not args.end_date:
                parser.error("--start-date and --end-date are required unless --list-sessions is used")
            backup_path = _backup_database(db_path) if args.apply and args.backup else None
            if args.create_missing:
                report = create_missing_practice_records(
                    conn,
                    real_name=args.real_name,
                    start_date=args.start_date,
                    end_date=args.end_date,
                    apply_changes=args.apply,
                    rng_seed=args.seed,
                )
            else:
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
