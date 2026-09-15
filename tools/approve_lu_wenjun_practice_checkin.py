"""Approve Lu Wenjun's 2026-09-15 82%-displayed final practice batch once."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


FIX_ID = "2026-09-15-lu-wenjun-practice-82-percent-approval"
REAL_NAME = "陆文俊"


def _backup(db_path: Path) -> Path:
    target = db_path.with_name(
        f"{db_path.stem}.before-{FIX_ID}-{datetime.now():%Y%m%d-%H%M%S}{db_path.suffix}"
    )
    shutil.copy2(db_path, target)
    return target


def _ensure_support_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS data_fix_runs (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS exam_daily_checkin_approvals (
            user_id INTEGER NOT NULL,
            target_date TEXT NOT NULL,
            approved_accuracy REAL,
            reason TEXT NOT NULL,
            approved_by TEXT NOT NULL,
            approved_at TEXT NOT NULL,
            PRIMARY KEY (user_id, target_date)
        )
        """
    )


def approve_checkin(db_path: Path, target_date: str, apply_changes: bool, backup: bool) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_support_tables(conn)
        existing = conn.execute(
            "SELECT applied_at FROM data_fix_runs WHERE id = ?", (FIX_ID,)
        ).fetchone()
        if existing:
            return {"status": "skipped", "fix_id": FIX_ID, "applied_at": existing["applied_at"]}

        users = conn.execute(
            "SELECT id, username, real_name FROM users WHERE real_name = ?", (REAL_NAME,)
        ).fetchall()
        if len(users) != 1:
            raise ValueError(f"姓名 {REAL_NAME} 匹配到 {len(users)} 位用户，拒绝审批")
        user = users[0]
        sessions = conn.execute(
            """
            SELECT COALESCE(practice_session_id, CAST(id AS TEXT)) AS session_id,
                   COUNT(*) AS total_count,
                   SUM(COALESCE(accuracy_credit, CASE WHEN is_correct = 1 THEN 1 ELSE 0 END)) AS accuracy_credit
            FROM exam_practice_attempts
            WHERE user_id = ? AND created_at LIKE ?
            GROUP BY COALESCE(practice_session_id, CAST(id AS TEXT))
            """,
            (user["id"], f"{target_date}%"),
        ).fetchall()
        normalized_sessions = [
            {
                "session_id": row["session_id"],
                "total_count": int(row["total_count"] or 0),
                "accuracy": round(float(row["accuracy_credit"] or 0) / int(row["total_count"] or 1), 4),
            }
            for row in sessions
        ]
        best_accuracy = max((item["accuracy"] for item in normalized_sessions), default=0.0)
        if not normalized_sessions or round(best_accuracy * 100) < 82:
            raise ValueError("未找到可按82%审批的当日练习记录，拒绝写入")
        report = {
            "fix_id": FIX_ID,
            "user": dict(user),
            "target_date": target_date,
            "sessions": normalized_sessions,
            "best_accuracy": best_accuracy,
        }
        if not apply_changes:
            return {"status": "dry-run", **report}

        backup_path = _backup(db_path) if backup else None
        conn.execute("BEGIN IMMEDIATE")
        approved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """
            INSERT INTO exam_daily_checkin_approvals (
                user_id, target_date, approved_accuracy, reason, approved_by, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, target_date) DO UPDATE SET
                approved_accuracy = excluded.approved_accuracy,
                reason = excluded.reason,
                approved_by = excluded.approved_by,
                approved_at = excluded.approved_at
            """,
            (
                user["id"], target_date, best_accuracy,
                "末批未做题不足30题，按显示82%正确率一次性审批合格",
                "系统管理员授权", approved_at,
            ),
        )
        conn.execute(
            "INSERT INTO data_fix_runs (id, applied_at) VALUES (?, ?)",
            (FIX_ID, approved_at),
        )
        conn.commit()
        verified = conn.execute(
            "SELECT approved_accuracy, reason FROM exam_daily_checkin_approvals WHERE user_id = ? AND target_date = ?",
            (user["id"], target_date),
        ).fetchone()
        if not verified:
            raise RuntimeError("审批记录写入后校验失败")
        return {"status": "applied", "backup": str(backup_path), **report}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--target-date", default="2026-09-15")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", action="store_true")
    args = parser.parse_args()
    result = approve_checkin(Path(args.db).resolve(), args.target_date, args.apply, args.backup)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
