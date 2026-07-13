"""Apply one-time exam data fixes recorded in deploy/data-fixes."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import config

    DEFAULT_DB_PATH = Path(config.DATABASE_PATH)
except Exception:
    DEFAULT_DB_PATH = ROOT / "零星材管理系统.db"

DEFAULT_FIX_DIR = ROOT / "deploy" / "data-fixes"
OBJECTIVE_TYPES = {"single_choice", "multiple_choice", "true_false"}


def ensure_data_fix_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS data_fix_runs (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def ensure_practice_support_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS exam_practice_wrong_questions (
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            wrong_count INTEGER NOT NULL DEFAULT 1,
            last_answer_text TEXT NOT NULL DEFAULT '',
            first_wrong_at TEXT,
            last_wrong_at TEXT,
            PRIMARY KEY (user_id, question_id)
        )
        """
    )
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(exam_practice_attempts)").fetchall()
    }
    if "accuracy_credit" not in columns:
        conn.execute("ALTER TABLE exam_practice_attempts ADD COLUMN accuracy_credit REAL DEFAULT 0")
    if "practice_session_id" not in columns:
        conn.execute("ALTER TABLE exam_practice_attempts ADD COLUMN practice_session_id TEXT")
    conn.commit()


def has_applied(conn: sqlite3.Connection, fix_id: str) -> bool:
    row = conn.execute("SELECT id FROM data_fix_runs WHERE id = ?", (fix_id,)).fetchone()
    return row is not None


def mark_applied(conn: sqlite3.Connection, fix_id: str) -> None:
    conn.execute(
        "INSERT INTO data_fix_runs (id, applied_at) VALUES (?, ?)",
        (fix_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )


def find_user(conn: sqlite3.Connection, user_key: str) -> sqlite3.Row:
    rows = conn.execute(
        """
        SELECT id, username, real_name
        FROM users
        WHERE lower(username) = lower(?)
           OR real_name = ?
        """,
        (user_key, user_key),
    ).fetchall()
    if not rows:
        raise ValueError(f"User not found: {user_key}")
    if len(rows) > 1:
        raise ValueError(f"User lookup is ambiguous: {user_key}")
    return rows[0]


def load_objective_questions(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    rows = conn.execute(
        f"""
        SELECT q.id, q.question_type, q.correct_answer
        FROM exam_questions q
        JOIN exam_papers p ON p.id = q.paper_id
        WHERE p.source_type = 'exam'
          AND q.question_type IN ({",".join("?" for _ in OBJECTIVE_TYPES)})
        ORDER BY p.id, q.order_no, q.id
        LIMIT ?
        """,
        [*sorted(OBJECTIVE_TYPES), limit],
    ).fetchall()
    if len(rows) < limit:
        raise ValueError(f"Not enough objective questions: need {limit}, found {len(rows)}")
    return rows


def wrong_answer(question: sqlite3.Row) -> str:
    correct = str(question["correct_answer"] or "").strip().upper()
    if question["question_type"] == "true_false":
        return "×" if correct in {"√", "正确", "对", "是", "TRUE", "T"} else "√"
    if question["question_type"] == "multiple_choice":
        option = next((candidate for candidate in "ABCDE" if candidate not in set(correct)), "Z")
        return option
    return "A" if correct != "A" else "B"


def set_daily_practice_status(conn: sqlite3.Connection, fix: dict) -> dict:
    ensure_practice_support_schema(conn)
    user = find_user(conn, fix["user"])
    date = fix["date"]
    answered_count = int(fix["answered_count"])
    display_accuracy_percent = int(fix["display_accuracy_percent"])
    correct_count = round(answered_count * display_accuracy_percent / 100)
    correct_count = max(0, min(answered_count, correct_count))
    questions = load_objective_questions(conn, answered_count)
    session_id = f"manual-{fix['id']}"
    created_at = f"{date} 09:00:00"
    question_ids = [row["id"] for row in questions]

    conn.execute(
        """
        DELETE FROM exam_practice_attempts
        WHERE user_id = ?
          AND created_at LIKE ?
        """,
        (user["id"], f"{date}%"),
    )
    conn.execute(
        f"""
        DELETE FROM exam_practice_wrong_questions
        WHERE user_id = ?
          AND question_id IN ({",".join("?" for _ in question_ids)})
        """,
        [user["id"], *question_ids],
    )

    rows = []
    wrong_rows = []
    for index, question in enumerate(questions):
        is_correct = index < correct_count
        answer_text = question["correct_answer"] if is_correct else wrong_answer(question)
        rows.append(
            (
                user["id"],
                question["id"],
                answer_text,
                1 if is_correct else 0,
                1.0 if is_correct else 0.0,
                created_at,
                session_id,
            )
        )
        if not is_correct:
            wrong_rows.append(
                (
                    user["id"],
                    question["id"],
                    answer_text,
                    created_at,
                    created_at,
                )
            )

    conn.executemany(
        """
        INSERT INTO exam_practice_attempts (
            user_id, question_id, answer_text, is_correct,
            accuracy_credit, created_at, practice_session_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.executemany(
        """
        INSERT INTO exam_practice_wrong_questions (
            user_id, question_id, wrong_count, last_answer_text,
            first_wrong_at, last_wrong_at
        ) VALUES (?, ?, 1, ?, ?, ?)
        ON CONFLICT(user_id, question_id) DO UPDATE SET
            wrong_count = 1,
            last_answer_text = excluded.last_answer_text,
            first_wrong_at = excluded.first_wrong_at,
            last_wrong_at = excluded.last_wrong_at
        """,
        wrong_rows,
    )
    return {
        "user_id": user["id"],
        "username": user["username"],
        "real_name": user["real_name"],
        "date": date,
        "answered_count": answered_count,
        "correct_count": correct_count,
        "display_accuracy_percent": round(correct_count / answered_count * 100) if answered_count else 0,
        "session_id": session_id,
    }


def apply_fix(conn: sqlite3.Connection, fix: dict, apply_changes: bool) -> dict:
    fix_id = fix["id"]
    if has_applied(conn, fix_id):
        return {"id": fix_id, "status": "skipped"}
    if fix.get("type") != "daily_practice_status":
        raise ValueError(f"Unsupported data fix type: {fix.get('type')}")
    result = set_daily_practice_status(conn, fix)
    if apply_changes:
        mark_applied(conn, fix_id)
        conn.commit()
        status = "applied"
    else:
        conn.rollback()
        status = "dry-run"
    return {"id": fix_id, "status": status, "result": result}


def load_fixes(fix_dir: Path) -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(fix_dir.glob("*.json"))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--fix-dir", default=str(DEFAULT_FIX_DIR), help="Directory containing JSON data fixes.")
    parser.add_argument("--apply", action="store_true", help="Persist unapplied fixes.")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    fix_dir = Path(args.fix_dir).resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    if not fix_dir.exists():
        print(json.dumps({"mode": "apply" if args.apply else "dry-run", "fixes": []}, ensure_ascii=False, indent=2))
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        ensure_data_fix_table(conn)
        results = [apply_fix(conn, fix, apply_changes=args.apply) for fix in load_fixes(fix_dir)]
    finally:
        conn.close()

    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "fixes": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
