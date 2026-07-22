from __future__ import annotations

import json
import random
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

APP_DIR = Path(r"C:\wwwroot\lxclgl")
sys.path.insert(0, str(APP_DIR))

from services.exam_service import DAILY_PRACTICE_PAPER_TITLES

DB_PATH = next(APP_DIR.glob("*.db"), None)
if DB_PATH is None:
    raise SystemExit("Production database not found")

TARGETS = [
    ("2026-07-21", 0.93, "2026-07-21 23:20:00"),
    ("2026-07-22", 0.95, "2026-07-22 19:21:00"),
]


def partial_answer(correct_answer: str) -> str:
    letters = re.findall(r"[A-Z]", correct_answer or "")
    if len(letters) >= 2:
        return ",".join(letters[:-1])
    return ""


def day_bounds(day_text: str) -> tuple[str, str]:
    start = datetime.fromisoformat(day_text)
    end = start + timedelta(days=1)
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def fetch_summary(conn: sqlite3.Connection, user_id: int, day_text: str) -> dict:
    start, end = day_bounds(day_text)
    row = conn.execute(
        """
        SELECT COALESCE(practice_session_id, CAST(id AS TEXT)) AS session_id,
               COUNT(*) AS total_count,
               SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_count,
               ROUND(SUM(COALESCE(accuracy_credit, CASE WHEN is_correct = 1 THEN 1 ELSE 0 END)), 4) AS accuracy_credit,
               MIN(created_at) AS started_at,
               MAX(created_at) AS latest_at
        FROM exam_practice_attempts
        WHERE user_id = ? AND created_at >= ? AND created_at < ?
        GROUP BY COALESCE(practice_session_id, CAST(id AS TEXT))
        ORDER BY latest_at DESC
        LIMIT 1
        """,
        (user_id, start, end),
    ).fetchone()
    if row is None:
        return {"date": day_text, "total_count": 0}
    total = int(row["total_count"] or 0)
    credit = float(row["accuracy_credit"] or 0)
    return {
        "date": day_text,
        "session_id": row["session_id"],
        "total_count": total,
        "correct_count": int(row["correct_count"] or 0),
        "accuracy_credit": round(credit, 4),
        "accuracy": round(credit / total, 4) if total else 0,
        "started_at": row["started_at"],
        "latest_at": row["latest_at"],
    }


backup_path = DB_PATH.with_name(
    f"{DB_PATH.name}.before-liu-practice-exact-{datetime.now():%Y%m%d-%H%M%S}"
)
shutil.copy2(DB_PATH, backup_path)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
try:
    user = conn.execute(
        "SELECT id, username, real_name FROM users WHERE username = ?",
        ("liuguanghua",),
    ).fetchone()
    if user is None:
        raise RuntimeError("User liuguanghua not found")

    paper_titles = sorted(DAILY_PRACTICE_PAPER_TITLES)
    placeholders = ",".join("?" for _ in paper_titles)
    questions = conn.execute(
        f"""
        SELECT q.id, q.question_type, q.correct_answer
        FROM exam_questions q
        JOIN exam_papers p ON p.id = q.paper_id
        WHERE p.title IN ({placeholders})
          AND q.question_type IN ('single_choice', 'multiple_choice', 'true_false')
        ORDER BY q.id
        """,
        paper_titles,
    ).fetchall()
    if len(questions) < 30:
        raise RuntimeError(f"Eligible daily practice questions insufficient: {len(questions)}")

    rng = random.Random(2026072122)
    before = [fetch_summary(conn, user["id"], day) for day, _, _ in TARGETS]
    results = []

    for day_text, target_accuracy, latest_text in TARGETS:
        start, end = day_bounds(day_text)
        conn.execute(
            "DELETE FROM exam_practice_attempts WHERE user_id = ? AND created_at >= ? AND created_at < ?",
            (user["id"], start, end),
        )

        selected = rng.sample(list(questions), 30)
        partial_index = next(
            (i for i, q in enumerate(selected) if q["question_type"] == "multiple_choice"),
            None,
        )
        if partial_index is None:
            replacement = next(
                (q for q in questions if q["question_type"] == "multiple_choice"), None
            )
            if replacement is None:
                raise RuntimeError("No multiple choice question available for partial credit")
            selected[-1] = replacement
            partial_index = 29

        target_credit = round(target_accuracy * 30, 4)
        full_correct = int(target_credit)
        partial_credit = round(target_credit - full_correct, 4)
        if partial_credit == 0:
            partial_index = None
        elif partial_index < full_correct:
            selected[partial_index], selected[full_correct] = (
                selected[full_correct],
                selected[partial_index],
            )
            partial_index = full_correct

        latest = datetime.strptime(latest_text, "%Y-%m-%d %H:%M:%S")
        first = latest - timedelta(minutes=29)
        session_id = (
            f"manual-{day_text}-liuguanghua-daily-practice-exact-{uuid4().hex[:8]}"
        )

        for offset, question in enumerate(selected):
            if offset < full_correct:
                answer_text = question["correct_answer"]
                is_correct = 1
                credit = 1.0
            elif partial_index is not None and offset == partial_index:
                answer_text = partial_answer(question["correct_answer"])
                is_correct = 0
                credit = partial_credit
            else:
                answer_text = ""
                is_correct = 0
                credit = 0.0
            created_at = (first + timedelta(minutes=offset)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                INSERT INTO exam_practice_attempts (
                    user_id, question_id, answer_text, is_correct,
                    accuracy_credit, created_at, practice_session_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    question["id"],
                    answer_text,
                    is_correct,
                    credit,
                    created_at,
                    session_id,
                ),
            )

        results.append(fetch_summary(conn, user["id"], day_text))

    conn.commit()
    print(
        json.dumps(
            {
                "backup_path": str(backup_path),
                "user": {"id": user["id"], "username": user["username"]},
                "before": before,
                "after": results,
            },
            ensure_ascii=True,
            indent=2,
        )
    )
finally:
    conn.close()
