"""Regrade saved exam and daily-practice attempts with current scoring rules."""

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

from services.exam_service import (
    EXAM_TOTAL_SCORE,
    OBJECTIVE_TYPES,
    SUBJECTIVE_TYPES,
    grade_objective,
    scale_exam_score,
    suggest_subjective_score,
)

try:
    import config

    DEFAULT_DB_PATH = Path(config.DATABASE_PATH)
except Exception:
    DEFAULT_DB_PATH = ROOT / "零星材管理系统.db"


def _needs_update(old_correct, old_credit, new_correct: int, new_credit: float) -> bool:
    current_correct = 1 if old_correct == 1 else 0
    current_credit = float(old_credit or 0)
    return current_correct != new_correct or abs(current_credit - new_credit) > 0.0001


def _float_changed(old_value, new_value: float | None) -> bool:
    if old_value is None and new_value is None:
        return False
    if old_value is None or new_value is None:
        return True
    return abs(float(old_value or 0) - float(new_value or 0)) > 0.0001


def _has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _ensure_practice_columns(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, "exam_practice_attempts"):
        return
    columns = _table_columns(conn, "exam_practice_attempts")
    changed = False
    if "practice_session_id" not in columns:
        conn.execute("ALTER TABLE exam_practice_attempts ADD COLUMN practice_session_id TEXT")
        changed = True
    if "accuracy_credit" not in columns:
        conn.execute("ALTER TABLE exam_practice_attempts ADD COLUMN accuracy_credit REAL DEFAULT 0")
        conn.execute(
            """
            UPDATE exam_practice_attempts
            SET accuracy_credit = CASE WHEN is_correct = 1 THEN 1 ELSE 0 END
            WHERE accuracy_credit IS NULL OR accuracy_credit = 0
            """
        )
        changed = True
    if changed:
        conn.commit()


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
    if not all(_has_table(conn, table) for table in {"exam_practice_attempts", "exam_questions", "users"}):
        return {
            "mode": "apply" if apply_changes else "dry-run",
            "total_attempts": 0,
            "practice_users": 0,
            "changed_attempts": 0,
            "affected_users": 0,
            "users": [],
            "updates": [],
            "sessions": [],
        }
    if apply_changes:
        _ensure_practice_columns(conn)
    practice_columns = _table_columns(conn, "exam_practice_attempts")
    accuracy_expr = (
        "pa.accuracy_credit"
        if "accuracy_credit" in practice_columns
        else "CASE WHEN pa.is_correct = 1 THEN 1 ELSE 0 END"
    )

    rows = conn.execute(
        f"""
        SELECT pa.id,
               pa.user_id,
               pa.question_id,
               pa.answer_text,
               pa.is_correct,
               {accuracy_expr} AS accuracy_credit,
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


def normalize_paper_totals(conn: sqlite3.Connection, apply_changes: bool = False) -> dict:
    conn.row_factory = sqlite3.Row
    if not _has_table(conn, "exam_papers"):
        return {"mode": "apply" if apply_changes else "dry-run", "total_papers": 0, "changed_papers": 0, "updates": []}

    rows = conn.execute(
        "SELECT id, title, total_score, source_type FROM exam_papers ORDER BY id"
    ).fetchall()
    updates = [
        {
            "paper_id": row["id"],
            "title": row["title"],
            "source_type": row["source_type"],
            "old_total_score": row["total_score"],
            "new_total_score": int(EXAM_TOTAL_SCORE),
        }
        for row in rows
        if int(row["total_score"] or 0) != int(EXAM_TOTAL_SCORE)
    ]
    if apply_changes and updates:
        conn.executemany(
            "UPDATE exam_papers SET total_score = ? WHERE id = ?",
            [(update["new_total_score"], update["paper_id"]) for update in updates],
        )
        conn.commit()
    return {
        "mode": "apply" if apply_changes else "dry-run",
        "total_papers": len(rows),
        "changed_papers": len(updates),
        "updates": updates,
    }


def _formal_answer_revisions(conn: sqlite3.Connection) -> tuple[list[dict], dict[int, dict]]:
    rows = conn.execute(
        """
        SELECT ans.id,
               ans.attempt_id,
               ans.question_id,
               ans.answer_text,
               ans.auto_score,
               ans.suggested_score,
               ans.final_score,
               q.question_type,
               q.correct_answer,
               q.keywords,
               q.score
        FROM exam_answers ans
        JOIN exam_questions q ON q.id = ans.question_id
        ORDER BY ans.id
        """
    ).fetchall()
    updates = []
    revisions = {}
    for row in rows:
        new_auto_score = float(row["auto_score"] or 0)
        new_suggested_score = float(row["suggested_score"] or 0)
        new_final_score = row["final_score"]
        if row["question_type"] in OBJECTIVE_TYPES:
            new_auto_score = grade_objective(
                row["question_type"],
                row["answer_text"],
                row["correct_answer"],
                row["score"],
            )
            new_final_score = new_auto_score
        elif row["question_type"] in SUBJECTIVE_TYPES:
            new_suggested_score, _ = suggest_subjective_score(
                row["answer_text"], row["keywords"], row["score"]
            )

        revision = {
            "answer_id": row["id"],
            "attempt_id": row["attempt_id"],
            "question_id": row["question_id"],
            "new_auto_score": new_auto_score,
            "new_suggested_score": new_suggested_score,
            "new_final_score": new_final_score,
        }
        revisions[row["id"]] = revision
        if (
            _float_changed(row["auto_score"], new_auto_score)
            or _float_changed(row["suggested_score"], new_suggested_score)
            or _float_changed(row["final_score"], new_final_score)
        ):
            updates.append(
                {
                    **revision,
                    "old_auto_score": row["auto_score"],
                    "old_suggested_score": row["suggested_score"],
                    "old_final_score": row["final_score"],
                }
            )
    return updates, revisions


def _attempt_total_updates(conn: sqlite3.Connection, answer_revisions: dict[int, dict]) -> list[dict]:
    attempts = conn.execute(
        """
        SELECT id, paper_id, status, objective_score,
               suggested_subjective_score, final_subjective_score, final_score
        FROM exam_attempts
        WHERE status != 'in_progress'
        ORDER BY id
        """
    ).fetchall()
    updates = []
    for attempt in attempts:
        rows = conn.execute(
            """
            SELECT q.id AS question_id,
                   q.question_type,
                   q.score,
                   ans.id AS answer_id,
                   ans.suggested_score,
                   ans.final_score
            FROM exam_questions q
            LEFT JOIN exam_answers ans
              ON ans.question_id = q.id
             AND ans.attempt_id = ?
            WHERE q.paper_id = ?
            ORDER BY q.order_no, q.id
            """,
            (attempt["id"], attempt["paper_id"]),
        ).fetchall()
        raw_total = sum(float(row["score"] or 0) for row in rows)
        objective_raw = 0.0
        suggested_subjective_raw = 0.0
        final_subjective_raw = 0.0
        has_subjective = False
        pending_subjective = False
        for row in rows:
            revision = answer_revisions.get(row["answer_id"] or -1, {})
            final_score = revision.get("new_final_score", row["final_score"])
            suggested_score = revision.get("new_suggested_score", row["suggested_score"])
            if row["question_type"] in OBJECTIVE_TYPES:
                objective_raw += float(final_score or 0)
            elif row["question_type"] in SUBJECTIVE_TYPES:
                has_subjective = True
                suggested_subjective_raw += float(suggested_score or 0)
                if final_score is None:
                    pending_subjective = True
                else:
                    final_subjective_raw += float(final_score or 0)

        new_objective_score = scale_exam_score(objective_raw, raw_total)
        new_suggested_subjective_score = scale_exam_score(suggested_subjective_raw, raw_total)
        if has_subjective and pending_subjective:
            new_final_subjective_score = None
            new_final_score = None
        elif has_subjective:
            new_final_subjective_score = scale_exam_score(final_subjective_raw, raw_total)
            new_final_score = scale_exam_score(objective_raw + final_subjective_raw, raw_total)
        else:
            new_final_subjective_score = None
            new_final_score = new_objective_score

        if (
            _float_changed(attempt["objective_score"], new_objective_score)
            or _float_changed(attempt["suggested_subjective_score"], new_suggested_subjective_score)
            or _float_changed(attempt["final_subjective_score"], new_final_subjective_score)
            or _float_changed(attempt["final_score"], new_final_score)
        ):
            updates.append(
                {
                    "attempt_id": attempt["id"],
                    "paper_id": attempt["paper_id"],
                    "status": attempt["status"],
                    "old_objective_score": attempt["objective_score"],
                    "new_objective_score": new_objective_score,
                    "old_suggested_subjective_score": attempt["suggested_subjective_score"],
                    "new_suggested_subjective_score": new_suggested_subjective_score,
                    "old_final_subjective_score": attempt["final_subjective_score"],
                    "new_final_subjective_score": new_final_subjective_score,
                    "old_final_score": attempt["final_score"],
                    "new_final_score": new_final_score,
                }
            )
    return updates


def regrade_formal_attempts(conn: sqlite3.Connection, apply_changes: bool = False) -> dict:
    conn.row_factory = sqlite3.Row
    required = {"exam_attempts", "exam_answers", "exam_questions"}
    if not all(_has_table(conn, table) for table in required):
        return {
            "mode": "apply" if apply_changes else "dry-run",
            "total_answers": 0,
            "changed_answers": 0,
            "changed_attempts": 0,
            "answer_updates": [],
            "attempt_updates": [],
        }

    answer_updates, answer_revisions = _formal_answer_revisions(conn)
    attempt_updates = _attempt_total_updates(conn, answer_revisions)

    if apply_changes:
        conn.executemany(
            """
            UPDATE exam_answers
            SET auto_score = ?, suggested_score = ?, final_score = ?
            WHERE id = ?
            """,
            [
                (
                    update["new_auto_score"],
                    update["new_suggested_score"],
                    update["new_final_score"],
                    update["answer_id"],
                )
                for update in answer_updates
            ],
        )
        conn.executemany(
            """
            UPDATE exam_attempts
            SET objective_score = ?,
                suggested_subjective_score = ?,
                final_subjective_score = ?,
                final_score = ?
            WHERE id = ?
            """,
            [
                (
                    update["new_objective_score"],
                    update["new_suggested_subjective_score"],
                    update["new_final_subjective_score"],
                    update["new_final_score"],
                    update["attempt_id"],
                )
                for update in attempt_updates
            ],
        )
        conn.commit()

    return {
        "mode": "apply" if apply_changes else "dry-run",
        "total_answers": len(answer_revisions),
        "changed_answers": len(answer_updates),
        "changed_attempts": len(attempt_updates),
        "answer_updates": answer_updates,
        "attempt_updates": attempt_updates,
    }


def regrade_all_exam_scores(conn: sqlite3.Connection, apply_changes: bool = False) -> dict:
    conn.row_factory = sqlite3.Row
    papers = normalize_paper_totals(conn, apply_changes=apply_changes)
    formal = regrade_formal_attempts(conn, apply_changes=apply_changes)
    practice = regrade_practice_attempts(conn, apply_changes=apply_changes)
    return {
        "mode": "apply" if apply_changes else "dry-run",
        "papers": papers,
        "formal": formal,
        "practice": practice,
    }


def backup_database(db_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.before-exam-regrade-{timestamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def _report_has_changes(report: dict) -> bool:
    return bool(
        report["papers"]["changed_papers"]
        or report["formal"]["changed_answers"]
        or report["formal"]["changed_attempts"]
        or report["practice"]["changed_attempts"]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--apply", action="store_true", help="Persist recalculated scores.")
    parser.add_argument("--backup", action="store_true", help="Copy the database before applying changes.")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        dry_run = regrade_all_exam_scores(conn, apply_changes=False)
        backup_path = None
        if args.apply and args.backup and _report_has_changes(dry_run):
            backup_path = backup_database(db_path)
        report = regrade_all_exam_scores(conn, apply_changes=args.apply)
    finally:
        conn.close()

    if backup_path:
        report["backup_path"] = str(backup_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
