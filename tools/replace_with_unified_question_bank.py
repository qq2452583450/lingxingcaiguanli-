"""Replace active exam sources with the supplied 220-question unified bank."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.exam_import_service import replace_active_practice_sources_with_unified_question_bank


FIX_ID = "2026-09-08-unified-question-bank-220"


def _backup(db_path: Path) -> Path:
    backup_path = db_path.with_name(
        f"{db_path.stem}.before-{FIX_ID}-{datetime.now():%Y%m%d-%H%M%S}{db_path.suffix}"
    )
    shutil.copy2(db_path, backup_path)
    return backup_path


def replace_question_bank(db_path: Path, apply_changes: bool, backup: bool) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS data_fix_runs (id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        already_applied = conn.execute(
            "SELECT applied_at FROM data_fix_runs WHERE id = ?", (FIX_ID,)
        ).fetchone()
        if already_applied:
            return {"status": "skipped", "fix_id": FIX_ID, "applied_at": already_applied["applied_at"]}
        if not apply_changes:
            return {"status": "dry-run", "fix_id": FIX_ID}

        backup_path = _backup(db_path) if backup else None
        conn.execute("BEGIN IMMEDIATE")
        result = replace_active_practice_sources_with_unified_question_bank(conn=conn, commit=False)
        if result["bank_question_count"] != 220:
            raise ValueError("Unified bank validation failed before commit")
        conn.execute(
            "INSERT INTO data_fix_runs (id, applied_at) VALUES (?, ?)",
            (FIX_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        return {
            "status": "applied",
            "fix_id": FIX_ID,
            "backup": str(backup_path) if backup_path else None,
            **result,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="SQLite database path")
    parser.add_argument("--apply", action="store_true", help="Persist the replacement")
    parser.add_argument("--backup", action="store_true", help="Back up the database before replacing")
    args = parser.parse_args()
    result = replace_question_bank(Path(args.db).resolve(), args.apply, args.backup)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
