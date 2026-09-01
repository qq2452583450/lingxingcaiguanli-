"""Exam center query and grading helpers."""

from __future__ import annotations

import json
import calendar
from datetime import date, datetime, timedelta
from uuid import uuid4


OBJECTIVE_TYPES = {"single_choice", "multiple_choice", "true_false"}
SUBJECTIVE_TYPES = {"short_answer", "case_analysis"}
EXAM_TOTAL_SCORE = 100.0
EXAM_PASSING_SCORE = 80.0
DAILY_PRACTICE_QUESTION_COUNT = 30
DAILY_PRACTICE_REQUIRED_ACCURACY = 0.8
MONTHLY_ATTENDANCE_REQUIRED_DAYS = 22
FORMAL_EXAM_POOL_SETTING_KEY = "formal_exam_pool_enabled"
FORMAL_EXAM_POOL_SOURCE_TYPE = "formal_exam_pool"
FORMAL_EXAM_POOL_REQUIRED_COUNT = 3
DAILY_PRACTICE_PAPER_TITLES = {
    "第一套（新编实操版）",
    "第二套（新编案例版）",
    "第三套（新编内控版）",
    "第四套（新编实操易错版）",
    "第五套（新编综合押题版）",
}
EXAM_TAKER_ROLES = {"材料员", "材料审批负责人", "基地负责人"}
EXAM_MANAGER_ROLES = {"系统管理员", "材料审批负责人"}
ATTENDANCE_REQUIRED_ROLES = {"材料员"}
_QUESTION_BANK_REFERENCE_SYNCED_FOR = None


def _connection():
    from helpers.db_helper import get_db

    try:
        return get_db(), False
    except RuntimeError:
        import sqlite3
        import config

        conn = sqlite3.connect(config.DATABASE_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn, True


def _dict_or_none(row):
    return dict(row) if row else None


def _sync_question_bank_references_once() -> None:
    global _QUESTION_BANK_REFERENCE_SYNCED_FOR
    try:
        import config

        database_path = str(config.DATABASE_PATH)
    except Exception:
        database_path = "__unknown__"
    if _QUESTION_BANK_REFERENCE_SYNCED_FOR == database_path:
        return
    try:
        from services.exam_import_service import (
            sync_question_bank_reference_answers,
        )

        sync_question_bank_reference_answers()
    except Exception:
        return
    _QUESTION_BANK_REFERENCE_SYNCED_FOR = database_path


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today_prefix() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError("Invalid date, expected YYYY-MM-DD")


def _parse_month(value: str | None) -> tuple[int, int, str]:
    raw = value or datetime.now().strftime("%Y-%m")
    try:
        parsed = datetime.strptime(raw, "%Y-%m")
    except (TypeError, ValueError):
        raise ValueError("Invalid month, expected YYYY-MM")
    return parsed.year, parsed.month, parsed.strftime("%Y-%m")


def _date_time_for_day(day: date) -> str:
    now = datetime.now()
    return f"{day.strftime('%Y-%m-%d')} {now.strftime('%H:%M:%S')}"


def _month_range(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    return first, last


def _answer_to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(item) for item in value)
    return str(value)


def _normalize_question_ids(question_ids) -> list[int]:
    normalized = []
    seen = set()
    for raw_id in question_ids or []:
        try:
            question_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if question_id > 0 and question_id not in seen:
            normalized.append(question_id)
            seen.add(question_id)
    return normalized


def _load_practice_questions_by_ids(conn, question_ids: list[int]) -> list[dict]:
    if not question_ids:
        return []
    placeholders = ",".join("?" for _ in question_ids)
    rows = conn.execute(
        f"""
        SELECT q.id, q.paper_id, p.title AS paper_title, q.question_type,
               q.order_no, q.stem, q.correct_answer, q.reference_answer,
               q.keywords, q.score
        FROM exam_questions q
        JOIN exam_papers p ON p.id = q.paper_id
        WHERE q.id IN ({placeholders})
          AND q.question_type IN ('single_choice', 'multiple_choice', 'true_false')
        """,
        question_ids,
    ).fetchall()
    questions_by_id = {row["id"]: dict(row) for row in rows}
    if len(questions_by_id) != len(question_ids):
        raise ValueError("Practice draft contains unknown or unsupported questions")
    ordered = [questions_by_id[question_id] for question_id in question_ids]
    for question in ordered:
        option_rows = conn.execute(
            """
            SELECT option_key, option_text
            FROM exam_question_options
            WHERE question_id = ?
            ORDER BY option_key
            """,
            (question["id"],),
        ).fetchall()
        question["options"] = [
            {"key": row["option_key"], "text": row["option_text"]}
            for row in option_rows
        ]
    return [ensure_question_options(question) for question in ordered]


def ensure_question_options(question: dict) -> dict:
    if question.get("question_type") == "true_false" and not question.get("options"):
        question = dict(question)
        question["options"] = [
            {"key": "√", "text": "正确"},
            {"key": "×", "text": "错误"},
        ]
    return question


def can_take_exam(user) -> bool:
    return (user or {}).get("role_name") in EXAM_TAKER_ROLES


def can_manage_exam(user) -> bool:
    return (user or {}).get("role_name") in EXAM_MANAGER_ROLES


def _role_placeholders(roles) -> str:
    return ",".join("?" for _ in roles)


def list_papers() -> list[dict]:
    conn, should_close = _connection()
    try:
        rows = conn.execute(
            """
            SELECT id, title, duration_minutes, total_score, source_type, create_time
            FROM exam_papers
            WHERE source_type != 'archived_exam'
            ORDER BY id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if should_close:
            conn.close()


def get_exam_paper(paper_id: int) -> dict | None:
    conn, should_close = _connection()
    try:
        row = conn.execute(
            """
            SELECT id, title, duration_minutes, total_score, source_type, create_time
            FROM exam_papers
            WHERE id = ?
            """,
            (paper_id,),
        ).fetchone()
        return _dict_or_none(row)
    finally:
        if should_close:
            conn.close()


def get_current_exam_paper() -> dict | None:
    conn, should_close = _connection()
    try:
        row = conn.execute(
            """
            SELECT p.id, p.title, p.duration_minutes, p.total_score, p.source_type, p.create_time
            FROM exam_settings s
            JOIN exam_papers p ON p.id = CAST(s.value AS INTEGER)
            WHERE s.key = ?
              AND p.source_type = 'exam'
            """,
            ("current_exam_paper_id",),
        ).fetchone()
        return _dict_or_none(row)
    finally:
        if should_close:
            conn.close()


def get_formal_exam_pool_status() -> dict:
    conn, should_close = _connection()
    try:
        setting = conn.execute(
            "SELECT value FROM exam_settings WHERE key = ?",
            (FORMAL_EXAM_POOL_SETTING_KEY,),
        ).fetchone()
        row = conn.execute(
            """
            SELECT COUNT(*) AS paper_count,
                   MIN(duration_minutes) AS duration_minutes,
                   MIN(total_score) AS total_score
            FROM exam_papers
            WHERE source_type = ?
            """,
            (FORMAL_EXAM_POOL_SOURCE_TYPE,),
        ).fetchone()
        paper_count = int(row["paper_count"] or 0)
        configured = bool(setting and setting["value"] == "1")
        return {
            "enabled": configured and paper_count == FORMAL_EXAM_POOL_REQUIRED_COUNT,
            "configured": configured,
            "paper_count": paper_count,
            "duration_minutes": row["duration_minutes"],
            "total_score": row["total_score"],
        }
    finally:
        if should_close:
            conn.close()


def get_random_formal_exam_paper() -> dict | None:
    if not get_formal_exam_pool_status()["enabled"]:
        return None
    conn, should_close = _connection()
    try:
        row = conn.execute(
            """
            SELECT id, title, duration_minutes, total_score, source_type, create_time
            FROM exam_papers
            WHERE source_type = ?
            ORDER BY RANDOM()
            LIMIT 1
            """,
            (FORMAL_EXAM_POOL_SOURCE_TYPE,),
        ).fetchone()
        return _dict_or_none(row)
    finally:
        if should_close:
            conn.close()


def get_paper_questions(paper_id: int) -> list[dict]:
    conn, should_close = _connection()
    try:
        question_rows = conn.execute(
            """
            SELECT id, paper_id, question_type, order_no, stem, correct_answer,
                   reference_answer, keywords, score
            FROM exam_questions
            WHERE paper_id = ?
            ORDER BY order_no
            """,
            (paper_id,),
        ).fetchall()
        questions = [dict(row) for row in question_rows]

        for question in questions:
            option_rows = conn.execute(
                """
                SELECT option_key, option_text
                FROM exam_question_options
                WHERE question_id = ?
                ORDER BY option_key
                """,
                (question["id"],),
            ).fetchall()
            question["options"] = [
                {"key": row["option_key"], "text": row["option_text"]}
                for row in option_rows
            ]

        return [ensure_question_options(question) for question in questions]
    finally:
        if should_close:
            conn.close()


def get_random_practice_questions(limit=10, paper_id=None) -> list[dict]:
    conn, should_close = _connection()
    try:
        params = []
        where_parts = ["q.question_type IN ('single_choice', 'multiple_choice', 'true_false')"]
        title_placeholders = ",".join("?" for _ in DAILY_PRACTICE_PAPER_TITLES)
        where_parts.append(f"p.title IN ({title_placeholders})")
        params.extend(sorted(DAILY_PRACTICE_PAPER_TITLES))
        if paper_id is not None:
            where_parts.append("q.paper_id = ?")
            params.append(paper_id)
        where = "WHERE " + " AND ".join(where_parts)
        params.append(limit)
        question_rows = conn.execute(
            f"""
            SELECT q.id, q.paper_id, p.title AS paper_title, q.question_type,
                   q.order_no, q.stem, q.correct_answer, q.reference_answer,
                   q.keywords, q.score
            FROM exam_questions q
            JOIN exam_papers p ON p.id = q.paper_id
            {where}
            ORDER BY RANDOM()
            LIMIT ?
            """,
            params,
        ).fetchall()
        questions = [dict(row) for row in question_rows]
        for question in questions:
            option_rows = conn.execute(
                """
                SELECT option_key, option_text
                FROM exam_question_options
                WHERE question_id = ?
                ORDER BY option_key
                """,
                (question["id"],),
            ).fetchall()
            question["options"] = [
                {"key": row["option_key"], "text": row["option_text"]}
                for row in option_rows
            ]
        return [ensure_question_options(question) for question in questions]
    finally:
        if should_close:
            conn.close()


def _load_objective_questions_by_ids(conn, question_ids: list[int]) -> dict[int, dict]:
    if not question_ids:
        raise ValueError("No practice answers submitted")
    placeholders = ",".join("?" for _ in question_ids)
    rows = conn.execute(
        f"""
        SELECT q.id, q.paper_id, p.title AS paper_title, q.question_type,
               q.order_no, q.stem, q.correct_answer, q.reference_answer,
               q.keywords, q.score
        FROM exam_questions q
        JOIN exam_papers p ON p.id = q.paper_id
        WHERE q.id IN ({placeholders})
          AND q.question_type IN ('single_choice', 'multiple_choice', 'true_false')
        """,
        question_ids,
    ).fetchall()
    questions = {row["id"]: dict(row) for row in rows}
    if len(questions) != len(set(question_ids)):
        raise ValueError("Practice answers contain unknown or unsupported questions")
    for question in questions.values():
        option_rows = conn.execute(
            """
            SELECT option_key, option_text
            FROM exam_question_options
            WHERE question_id = ?
            ORDER BY option_key
            """,
            (question["id"],),
        ).fetchall()
        question["options"] = [
            {"key": row["option_key"], "text": row["option_text"]}
            for row in option_rows
        ]
    return {
        question_id: ensure_question_options(question)
        for question_id, question in questions.items()
    }


def _generated_objective_explanation(question: dict) -> str:
    correct_answer = str(question.get("correct_answer") or "").strip()
    option_by_key = {
        str(option.get("key") or ""): str(option.get("text") or "").strip()
        for option in question.get("options", [])
    }
    normalized_answer = correct_answer.replace("，", ",").replace(" ", "")
    keys = [key for key in normalized_answer.split(",") if key] if "," in normalized_answer else list(normalized_answer)
    explanations = [
        f"{key}：{option_by_key[key]}"
        for key in keys
        if option_by_key.get(key)
    ]
    if not explanations:
        return f"本题正确答案为：{correct_answer}。"
    if question.get("question_type") == "multiple_choice":
        return (
            f"本题为多选题，正确答案为 {correct_answer}。"
            f"各正确选项说明：{'；'.join(explanations)}。"
            "其余选项不符合题干所述的管理要求。"
        )
    if question.get("question_type") == "true_false":
        return f"本题正确答案为 {correct_answer}。判断依据：{'；'.join(explanations)}。"
    return (
        f"本题正确答案为 {correct_answer}。"
        f"正确依据：{'；'.join(explanations)}。"
        "其余选项与题干要求不符。"
    )


def _practice_item(
    question: dict,
    answer_text: str,
    is_correct: bool,
    created_at: str,
    session_id: str | None,
    accuracy_credit: float | None = None,
) -> dict:
    credit = 1.0 if is_correct else 0.0
    if accuracy_credit is not None:
        credit = round(float(accuracy_credit), 4)
    reference_answer = str(question.get("reference_answer") or "").strip()
    if not reference_answer:
        reference_answer = _generated_objective_explanation(question)
    return {
        "session_id": session_id,
        "question_id": question["id"],
        "paper_id": question["paper_id"],
        "paper_title": question["paper_title"],
        "question_type": question["question_type"],
        "order_no": question["order_no"],
        "stem": question["stem"],
        "options": question.get("options", []),
        "answer_text": answer_text,
        "correct_answer": question["correct_answer"],
        "reference_answer": reference_answer,
        "is_correct": bool(is_correct),
        "accuracy_credit": credit,
        "score": question["score"],
        "created_at": created_at,
    }


def _record_practice_answers_for_date(
    user_id: int,
    answers: dict,
    target_day: date | None = None,
    retroactive: bool = False,
) -> dict:
    _sync_question_bank_references_once()
    answer_map = {str(key): _answer_to_text(value) for key, value in (answers or {}).items()}
    question_ids = [int(question_id) for question_id in answer_map.keys()]
    conn, should_close = _connection()
    try:
        questions = _load_objective_questions_by_ids(conn, question_ids)
        session_id = uuid4().hex
        created_at = _date_time_for_day(target_day) if target_day else _now()
        items = []
        for question_id in question_ids:
            question = questions[question_id]
            answer_text = answer_map[str(question_id)]
            earned_score = grade_objective(
                question["question_type"],
                answer_text,
                question["correct_answer"],
                question["score"],
            )
            is_correct = earned_score == float(question["score"])
            accuracy_credit = round(earned_score / float(question["score"]), 4) if question["score"] else 0.0
            conn.execute(
                """
                INSERT INTO exam_practice_attempts (
                    user_id, question_id, answer_text, is_correct,
                    accuracy_credit, created_at, practice_session_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, question_id, answer_text, 1 if is_correct else 0, accuracy_credit, created_at, session_id),
            )
            if is_correct:
                conn.execute(
                    "DELETE FROM exam_practice_wrong_questions WHERE user_id = ? AND question_id = ?",
                    (user_id, question_id),
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
                    (user_id, question_id, answer_text, created_at, created_at),
                )
            items.append(_practice_item(question, answer_text, is_correct, created_at, session_id, accuracy_credit))
        total_count = len(items)
        correct_count = sum(1 for item in items if item["is_correct"])
        accuracy_credit = sum(float(item["accuracy_credit"]) for item in items)
        accuracy = round(accuracy_credit / total_count, 4) if total_count else 0.0
        passed = (
            total_count >= DAILY_PRACTICE_QUESTION_COUNT
            and accuracy >= DAILY_PRACTICE_REQUIRED_ACCURACY
        )
        if retroactive and target_day:
            target_date = target_day.strftime("%Y-%m-%d")
            month = target_day.strftime("%Y-%m")
            if passed:
                conn.execute(
                    """
                    INSERT INTO exam_retroactive_checkins (
                        user_id, target_date, month, practice_session_id,
                        total_count, correct_count, accuracy, passed, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        target_date,
                        month,
                        session_id,
                        total_count,
                        correct_count,
                        accuracy,
                        1,
                        _now(),
                    ),
                )
        clear_practice_draft(user_id, conn=conn)
        conn.commit()
        return {
            "session_id": session_id,
            "items": items,
            "total_count": total_count,
            "correct_count": correct_count,
            "accuracy": accuracy,
            "required_accuracy": DAILY_PRACTICE_REQUIRED_ACCURACY,
            "passed": passed,
            "target_date": target_day.strftime("%Y-%m-%d") if target_day else _today_prefix(),
            "retroactive": retroactive,
            "daily_status": get_daily_practice_status(user_id, conn=conn),
        }
    finally:
        if should_close:
            conn.close()


def record_practice_answers(user_id: int, answers: dict) -> dict:
    return _record_practice_answers_for_date(user_id, answers)


def save_practice_draft(user_id: int, question_ids, answers: dict) -> dict:
    normalized_ids = _normalize_question_ids(question_ids)
    answer_map = {
        str(key): _answer_to_text(value)
        for key, value in (answers or {}).items()
        if str(key) in {str(question_id) for question_id in normalized_ids}
    }
    conn, should_close = _connection()
    try:
        questions = _load_practice_questions_by_ids(conn, normalized_ids)
        updated_at = _now()
        conn.execute(
            """
            INSERT INTO exam_practice_drafts (
                user_id, question_ids, answers_json, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                question_ids = excluded.question_ids,
                answers_json = excluded.answers_json,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                json.dumps(normalized_ids, ensure_ascii=False),
                json.dumps(answer_map, ensure_ascii=False),
                updated_at,
            ),
        )
        conn.commit()
        return {
            "question_ids": normalized_ids,
            "questions": questions,
            "answers": answer_map,
            "updated_at": updated_at,
        }
    finally:
        if should_close:
            conn.close()


def get_practice_draft(user_id: int) -> dict | None:
    conn, should_close = _connection()
    try:
        row = conn.execute(
            """
            SELECT question_ids, answers_json, updated_at
            FROM exam_practice_drafts
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if not row:
            return None
        question_ids = _normalize_question_ids(json.loads(row["question_ids"] or "[]"))
        answers = json.loads(row["answers_json"] or "{}")
        return {
            "question_ids": question_ids,
            "questions": _load_practice_questions_by_ids(conn, question_ids),
            "answers": {str(key): _answer_to_text(value) for key, value in answers.items()},
            "updated_at": row["updated_at"],
        }
    finally:
        if should_close:
            conn.close()


def clear_practice_draft(user_id: int, conn=None) -> None:
    should_close = False
    if conn is None:
        conn, should_close = _connection()
    try:
        conn.execute("DELETE FROM exam_practice_drafts WHERE user_id = ?", (user_id,))
        if should_close:
            conn.commit()
    finally:
        if should_close:
            conn.close()


def get_daily_practice_status(user_id: int, conn=None) -> dict:
    should_close = False
    if conn is None:
        conn, should_close = _connection()
    try:
        rows = conn.execute(
            """
            SELECT COALESCE(practice_session_id, CAST(id AS TEXT)) AS session_id,
                   COUNT(*) AS total_count,
                   SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_count,
                   SUM(COALESCE(accuracy_credit, CASE WHEN is_correct = 1 THEN 1 ELSE 0 END)) AS accuracy_credit,
                   MIN(created_at) AS started_at
            FROM exam_practice_attempts
            WHERE user_id = ?
              AND created_at LIKE ?
            GROUP BY COALESCE(practice_session_id, CAST(id AS TEXT))
            ORDER BY started_at DESC
            """,
            (user_id, f"{_today_prefix()}%"),
        ).fetchall()
        sessions = []
        for row in rows:
            total_count = int(row["total_count"] or 0)
            correct_count = int(row["correct_count"] or 0)
            accuracy_credit = float(row["accuracy_credit"] or 0)
            accuracy = round(accuracy_credit / total_count, 4) if total_count else 0.0
            sessions.append(
                {
                    "session_id": row["session_id"],
                    "total_count": total_count,
                    "correct_count": correct_count,
                    "accuracy": accuracy,
                    "passed": (
                        total_count >= DAILY_PRACTICE_QUESTION_COUNT
                        and accuracy >= DAILY_PRACTICE_REQUIRED_ACCURACY
                    ),
                    "started_at": row["started_at"],
                }
            )
        best_accuracy = max((session["accuracy"] for session in sessions), default=0.0)
        return {
            "date": _today_prefix(),
            "passed": any(session["passed"] for session in sessions),
            "best_accuracy": best_accuracy,
            "session_count": len(sessions),
            "answered_count": sum(session["total_count"] for session in sessions),
            "required_accuracy": DAILY_PRACTICE_REQUIRED_ACCURACY,
            "required_question_count": DAILY_PRACTICE_QUESTION_COUNT,
            "sessions": sessions,
        }
    finally:
        if should_close:
            conn.close()


def list_daily_checkins(target_date: str | None = None) -> list[dict]:
    date_prefix = target_date or _today_prefix()
    conn, should_close = _connection()
    try:
        roles = sorted(ATTENDANCE_REQUIRED_ROLES)
        users = conn.execute(
            f"""
            SELECT u.id, u.username, u.real_name, r.role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE COALESCE(u.is_active, 1) = 1
              AND r.role_name IN ({_role_placeholders(roles)})
            ORDER BY r.role_name, u.real_name, u.username
            """,
            roles,
        ).fetchall()
        rows = conn.execute(
            """
            SELECT user_id,
                   COALESCE(practice_session_id, CAST(id AS TEXT)) AS session_id,
                   COUNT(*) AS total_count,
                   SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_count,
                   SUM(COALESCE(accuracy_credit, CASE WHEN is_correct = 1 THEN 1 ELSE 0 END)) AS accuracy_credit,
                   MIN(created_at) AS started_at,
                   MAX(created_at) AS latest_at
            FROM exam_practice_attempts
            WHERE created_at LIKE ?
            GROUP BY user_id, COALESCE(practice_session_id, CAST(id AS TEXT))
            """,
            (f"{date_prefix}%",),
        ).fetchall()
        sessions_by_user: dict[int, list[dict]] = {}
        for row in rows:
            total_count = int(row["total_count"] or 0)
            correct_count = int(row["correct_count"] or 0)
            accuracy_credit = float(row["accuracy_credit"] or 0)
            accuracy = round(accuracy_credit / total_count, 4) if total_count else 0.0
            session = {
                "session_id": row["session_id"],
                "total_count": total_count,
                "correct_count": correct_count,
                "accuracy": accuracy,
                "passed": (
                    total_count >= DAILY_PRACTICE_QUESTION_COUNT
                    and accuracy >= DAILY_PRACTICE_REQUIRED_ACCURACY
                ),
                "started_at": row["started_at"],
                "latest_at": row["latest_at"],
            }
            sessions_by_user.setdefault(row["user_id"], []).append(session)

        report = []
        for user in users:
            sessions = sessions_by_user.get(user["id"], [])
            answered_count = sum(session["total_count"] for session in sessions)
            best_accuracy = max((session["accuracy"] for session in sessions), default=0.0)
            latest_practice_at = max(
                (session["latest_at"] for session in sessions if session["latest_at"]),
                default=None,
            )
            passed = any(session["passed"] for session in sessions)
            practiced = bool(sessions)
            report.append(
                {
                    "user_id": user["id"],
                    "username": user["username"],
                    "real_name": user["real_name"],
                    "role_name": user["role_name"],
                    "date": date_prefix,
                    "practiced": practiced,
                    "passed": passed,
                    "status": "passed" if passed else ("failed" if practiced else "missing"),
                    "answered_count": answered_count,
                    "session_count": len(sessions),
                    "best_accuracy": best_accuracy,
                    "latest_practice_at": latest_practice_at,
                    "required_accuracy": DAILY_PRACTICE_REQUIRED_ACCURACY,
                    "required_question_count": DAILY_PRACTICE_QUESTION_COUNT,
                }
            )
        return report
    finally:
        if should_close:
            conn.close()


def _practice_sessions_for_range(conn, user_id: int, start_day: date, end_day: date) -> dict[str, list[dict]]:
    rows = conn.execute(
        """
        SELECT substr(created_at, 1, 10) AS practice_date,
               COALESCE(practice_session_id, CAST(id AS TEXT)) AS session_id,
               COUNT(*) AS total_count,
               SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_count,
               SUM(COALESCE(accuracy_credit, CASE WHEN is_correct = 1 THEN 1 ELSE 0 END)) AS accuracy_credit,
               MIN(created_at) AS started_at,
               MAX(created_at) AS latest_at
        FROM exam_practice_attempts
        WHERE user_id = ?
          AND created_at >= ?
          AND created_at < ?
        GROUP BY substr(created_at, 1, 10), COALESCE(practice_session_id, CAST(id AS TEXT))
        """,
        (
            user_id,
            start_day.strftime("%Y-%m-%d 00:00:00"),
            (end_day + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00"),
        ),
    ).fetchall()
    sessions_by_date: dict[str, list[dict]] = {}
    for row in rows:
        total_count = int(row["total_count"] or 0)
        correct_count = int(row["correct_count"] or 0)
        accuracy_credit = float(row["accuracy_credit"] or 0)
        accuracy = round(accuracy_credit / total_count, 4) if total_count else 0.0
        session = {
            "session_id": row["session_id"],
            "total_count": total_count,
            "correct_count": correct_count,
            "accuracy": accuracy,
            "passed": (
                total_count >= DAILY_PRACTICE_QUESTION_COUNT
                and accuracy >= DAILY_PRACTICE_REQUIRED_ACCURACY
            ),
            "started_at": row["started_at"],
            "latest_at": row["latest_at"],
        }
        sessions_by_date.setdefault(row["practice_date"], []).append(session)
    return sessions_by_date


def _summarize_calendar_days(sessions_by_date: dict[str, list[dict]], start_day: date, end_day: date) -> dict:
    today = date.today()
    days = []
    actual_days = 0
    missing_days = 0
    cursor_day = start_day
    while cursor_day <= end_day:
        day_key = cursor_day.strftime("%Y-%m-%d")
        sessions = sessions_by_date.get(day_key, [])
        passed = any(session["passed"] for session in sessions)
        practiced = bool(sessions)
        if cursor_day > today:
            status = "future"
        elif passed:
            status = "passed"
            actual_days += 1
        else:
            status = "failed" if practiced else "missing"
            missing_days += 1
        best_accuracy = max((session["accuracy"] for session in sessions), default=0.0)
        latest_at = max((session["latest_at"] for session in sessions if session["latest_at"]), default=None)
        days.append(
            {
                "date": day_key,
                "status": status,
                "passed": passed,
                "practiced": practiced,
                "retroactive_allowed": cursor_day < today and not passed,
                "answered_count": sum(session["total_count"] for session in sessions),
                "session_count": len(sessions),
                "best_accuracy": best_accuracy,
                "latest_practice_at": latest_at,
            }
        )
        cursor_day += timedelta(days=1)
    return {
        "days": days,
        "actual_days": actual_days,
        "missing_days": missing_days,
    }


def list_attendance_calendar(user_id: int, month: str | None = None) -> dict:
    year, month_number, month_key = _parse_month(month)
    start_day, end_day = _month_range(year, month_number)
    conn, should_close = _connection()
    try:
        sessions_by_date = _practice_sessions_for_range(conn, user_id, start_day, end_day)
        summary = _summarize_calendar_days(sessions_by_date, start_day, end_day)
        retroactive_used = conn.execute(
            """
            SELECT COUNT(*)
            FROM exam_retroactive_checkins
            WHERE user_id = ?
              AND month = ?
              AND passed = 1
            """,
            (user_id, month_key),
        ).fetchone()[0]
        return {
            "month": month_key,
            "days": summary["days"],
            "actual_days": summary["actual_days"],
            "missing_days": summary["missing_days"],
            "retroactive_used": int(retroactive_used or 0),
            "required_accuracy": DAILY_PRACTICE_REQUIRED_ACCURACY,
            "required_question_count": DAILY_PRACTICE_QUESTION_COUNT,
        }
    finally:
        if should_close:
            conn.close()


def _has_passed_practice_on_date(conn, user_id: int, target_day: date) -> bool:
    sessions = _practice_sessions_for_range(conn, user_id, target_day, target_day)
    return any(session["passed"] for session in sessions.get(target_day.strftime("%Y-%m-%d"), []))


def submit_retroactive_checkin(user_id: int, target_date: str, answers: dict) -> dict:
    target_day = _parse_date(target_date)
    today = date.today()
    if target_day >= today:
        raise ValueError("Retroactive check-in is only available for past dates")
    conn, should_close = _connection()
    try:
        if _has_passed_practice_on_date(conn, user_id, target_day):
            raise ValueError("This date already has a qualified check-in")
    finally:
        if should_close:
            conn.close()

    result = _record_practice_answers_for_date(
        user_id,
        answers,
        target_day=target_day,
        retroactive=True,
    )
    result["attendance_calendar"] = list_attendance_calendar(
        user_id, target_day.strftime("%Y-%m")
    )
    return result


def list_monthly_checkin_reports(month: str | None = None) -> list[dict]:
    year, month_number, month_key = _parse_month(month)
    start_day, end_day = _month_range(year, month_number)
    completed_month = end_day < date.today()
    conn, should_close = _connection()
    try:
        roles = sorted(ATTENDANCE_REQUIRED_ROLES)
        users = conn.execute(
            f"""
            SELECT u.id, u.username, u.real_name, r.role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE COALESCE(u.is_active, 1) = 1
              AND r.role_name IN ({_role_placeholders(roles)})
            ORDER BY r.role_name, u.real_name, u.username
            """,
            roles,
        ).fetchall()
        reports = []
        for user in users:
            sessions_by_date = _practice_sessions_for_range(conn, user["id"], start_day, end_day)
            summary = _summarize_calendar_days(sessions_by_date, start_day, end_day)
            retroactive_dates = {
                row["target_date"]
                for row in conn.execute(
                    """
                    SELECT target_date
                    FROM exam_retroactive_checkins
                    WHERE user_id = ?
                      AND month = ?
                      AND passed = 1
                    """,
                    (user["id"], month_key),
                ).fetchall()
            }
            expected_days = MONTHLY_ATTENDANCE_REQUIRED_DAYS
            actual_days = summary["actual_days"]
            missing_days = max(expected_days - actual_days, 0)
            retroactive_used = conn.execute(
                """
                SELECT COUNT(*)
                FROM exam_retroactive_checkins
                WHERE user_id = ?
                  AND month = ?
                  AND passed = 1
                """,
                (user["id"], month_key),
            ).fetchone()[0]
            row = {
                "user_id": user["id"],
                "username": user["username"],
                "real_name": user["real_name"],
                "role_name": user["role_name"],
                "month": month_key,
                "expected_days": expected_days,
                "actual_days": actual_days,
                "missing_days": missing_days,
                "retroactive_used": int(retroactive_used or 0),
                "full_attendance": actual_days >= expected_days,
                "generated": completed_month,
                "days": [
                    {**day, "retroactive": day["date"] in retroactive_dates}
                    for day in summary["days"]
                ],
            }
            if completed_month:
                conn.execute(
                    """
                    INSERT INTO exam_monthly_checkin_reports (
                        user_id, month, expected_days, actual_days,
                        missing_days, retroactive_used, generated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, month) DO UPDATE SET
                        expected_days = excluded.expected_days,
                        actual_days = excluded.actual_days,
                        missing_days = excluded.missing_days,
                        retroactive_used = excluded.retroactive_used,
                        generated_at = excluded.generated_at
                    """,
                    (
                        user["id"],
                        month_key,
                        expected_days,
                        actual_days,
                        missing_days,
                        int(retroactive_used or 0),
                        _now(),
                    ),
                )
            reports.append(row)
        if completed_month:
            conn.commit()
        return reports
    finally:
        if should_close:
            conn.close()


def _practice_history_rows(user_id: int, limit: int) -> list[dict]:
    conn, should_close = _connection()
    try:
        rows = conn.execute(
            f"""
            SELECT pa.id, pa.practice_session_id, pa.answer_text, pa.is_correct,
                   COALESCE(pa.accuracy_credit, CASE WHEN pa.is_correct = 1 THEN 1 ELSE 0 END) AS accuracy_credit,
                   pa.created_at, q.id AS question_id, q.paper_id,
                   p.title AS paper_title, q.question_type, q.order_no,
                   q.stem, q.correct_answer, q.reference_answer, q.score
            FROM exam_practice_attempts pa
            JOIN exam_questions q ON q.id = pa.question_id
            JOIN exam_papers p ON p.id = q.paper_id
            WHERE pa.user_id = ?
            ORDER BY pa.created_at DESC, pa.id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        items = []
        for row in rows:
            question = dict(row)
            question["id"] = row["question_id"]
            option_rows = conn.execute(
                """
                SELECT option_key, option_text
                FROM exam_question_options
                WHERE question_id = ?
                ORDER BY option_key
                """,
                (row["question_id"],),
            ).fetchall()
            question["options"] = [
                {"key": option["option_key"], "text": option["option_text"]}
                for option in option_rows
            ]
            session_id = row["practice_session_id"] or str(row["id"])
            items.append(
                _practice_item(
                    ensure_question_options(question),
                    row["answer_text"],
                    bool(row["is_correct"]),
                    row["created_at"],
                    session_id,
                    row["accuracy_credit"],
                )
            )
        return items
    finally:
        if should_close:
            conn.close()


def list_practice_history(user_id: int, limit: int = 100) -> list[dict]:
    _sync_question_bank_references_once()
    return _practice_history_rows(user_id, limit=limit)


def list_wrong_practice_questions(user_id: int, limit: int = 100) -> list[dict]:
    _sync_question_bank_references_once()
    conn, should_close = _connection()
    try:
        rows = conn.execute(
            """
            SELECT w.question_id, w.wrong_count, w.last_answer_text, w.first_wrong_at,
                   w.last_wrong_at, q.paper_id, p.title AS paper_title,
                   q.question_type, q.order_no, q.stem, q.correct_answer,
                   q.reference_answer, q.score
            FROM exam_practice_wrong_questions w
            JOIN exam_questions q ON q.id = w.question_id
            JOIN exam_papers p ON p.id = q.paper_id
            WHERE w.user_id = ?
              AND p.source_type = 'exam'
            ORDER BY w.last_wrong_at DESC, w.question_id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        items = []
        for row in rows:
            question = dict(row)
            question["id"] = row["question_id"]
            option_rows = conn.execute(
                """
                SELECT option_key, option_text
                FROM exam_question_options
                WHERE question_id = ?
                ORDER BY option_key
                """,
                (row["question_id"],),
            ).fetchall()
            question["options"] = [
                {"key": option["option_key"], "text": option["option_text"]}
                for option in option_rows
            ]
            item = _practice_item(
                ensure_question_options(question),
                row["last_answer_text"],
                False,
                row["last_wrong_at"],
                None,
            )
            item["wrong_count"] = row["wrong_count"]
            item["first_wrong_at"] = row["first_wrong_at"]
            items.append(item)
        return items
    finally:
        if should_close:
            conn.close()


def list_material_clerk_wrong_questions(
    limit: int = 100,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Return material clerks' wrong questions, optionally counted within a date range."""
    _sync_question_bank_references_once()
    start_day = _parse_date(start_date) if start_date else None
    end_day = _parse_date(end_date) if end_date else None
    if start_day and end_day and start_day > end_day:
        raise ValueError("Start date cannot be later than end date")

    date_conditions = []
    date_params = []
    if start_day:
        date_conditions.append("wr.wrong_at >= ?")
        date_params.append(start_day.isoformat())
    if end_day:
        date_conditions.append("wr.wrong_at < ?")
        date_params.append((end_day + timedelta(days=1)).isoformat())
    date_where_sql = " AND " + " AND ".join(date_conditions) if date_conditions else ""
    practice_records_sql = """
                SELECT pa.question_id, pa.user_id, 1 AS wrong_count,
                       pa.answer_text,
                       pa.created_at AS wrong_at,
                       '平时打卡' AS source_label
                FROM exam_practice_attempts pa
                JOIN exam_questions q ON q.id = pa.question_id
                JOIN exam_papers p ON p.id = q.paper_id
                WHERE pa.is_correct = 0
                  AND p.source_type = 'exam'
    """ if date_conditions else """
                SELECT w.question_id, w.user_id, w.wrong_count,
                       w.last_answer_text AS answer_text,
                       w.last_wrong_at AS wrong_at,
                       '平时打卡' AS source_label
                FROM exam_practice_wrong_questions w
                JOIN exam_questions q ON q.id = w.question_id
                JOIN exam_papers p ON p.id = q.paper_id
                WHERE p.source_type = 'exam'
    """
    conn, should_close = _connection()
    try:
        rows = conn.execute(
            f"""
            WITH wrong_records AS (
                {practice_records_sql}

                UNION ALL

                SELECT ans.question_id, att.user_id, 1 AS wrong_count,
                       ans.answer_text,
                       COALESCE(att.submitted_at, att.started_at) AS wrong_at,
                       '正式考试' AS source_label
                FROM exam_answers ans
                JOIN exam_attempts att ON att.id = ans.attempt_id
                JOIN exam_questions q ON q.id = ans.question_id
                JOIN exam_papers p ON p.id = q.paper_id
                WHERE att.status = 'completed'
                  AND ans.final_score < q.score
            )
            SELECT wr.question_id, wr.user_id, wr.wrong_count, wr.answer_text,
                   wr.wrong_at, wr.source_label,
                   COALESCE(NULLIF(u.real_name, ''), u.username) AS user_name,
                   q.paper_id, p.title AS paper_title,
                   q.question_type, q.order_no, q.stem, q.correct_answer,
                   q.reference_answer, q.score
            FROM wrong_records wr
            JOIN users u ON u.id = wr.user_id
            JOIN roles r ON r.id = u.role_id
            JOIN exam_questions q ON q.id = wr.question_id
            JOIN exam_papers p ON p.id = q.paper_id
            WHERE r.role_name = '材料员'{date_where_sql}
            ORDER BY wr.wrong_at DESC, wr.question_id DESC
            """,
            date_params,
        ).fetchall()
        grouped = {}
        for row in rows:
            item = grouped.setdefault(
                row["question_id"],
                {
                    "question": dict(row),
                    "wrong_count": 0,
                    "last_wrong_at": row["wrong_at"],
                    "source_labels": set(),
                    "clerks": {},
                    "answer_details": [],
                },
            )
            item["wrong_count"] += int(row["wrong_count"] or 0)
            item["source_labels"].add(row["source_label"])
            if row["wrong_at"] > item["last_wrong_at"]:
                item["last_wrong_at"] = row["wrong_at"]
            clerk = item["clerks"].setdefault(row["user_id"], {"name": row["user_name"], "wrong_count": 0})
            clerk["wrong_count"] += int(row["wrong_count"] or 0)
            item["answer_details"].append(
                {
                    "user_name": row["user_name"],
                    "source_label": row["source_label"],
                    "wrong_count": int(row["wrong_count"] or 0),
                    "answer_text": row["answer_text"],
                }
            )

        items = []
        for group in sorted(
            grouped.values(),
            key=lambda item: (item["wrong_count"], item["last_wrong_at"]),
            reverse=True,
        )[:limit]:
            question = group["question"]
            question["id"] = question["question_id"]
            option_rows = conn.execute(
                """
                SELECT option_key, option_text
                FROM exam_question_options
                WHERE question_id = ?
                ORDER BY option_key
                """,
                (question["question_id"],),
            ).fetchall()
            question["options"] = [
                {"key": option["option_key"], "text": option["option_text"]}
                for option in option_rows
            ]
            item = _practice_item(
                ensure_question_options(question),
                "",
                False,
                group["last_wrong_at"],
                None,
            )
            item["wrong_count"] = group["wrong_count"]
            item["clerk_count"] = len(group["clerks"])
            item["clerk_details"] = "、".join(
                f"{clerk['name']}（{clerk['wrong_count']}次）"
                for clerk in group["clerks"].values()
            )
            item["source_labels"] = "、".join(sorted(group["source_labels"]))
            item["answer_details"] = group["answer_details"]
            items.append(item)
        return items
    finally:
        if should_close:
            conn.close()


def get_wrong_practice_questions_for_retry(user_id: int, limit: int = 100) -> list[dict]:
    _sync_question_bank_references_once()
    conn, should_close = _connection()
    try:
        rows = conn.execute(
            """
            SELECT question_id
            FROM exam_practice_wrong_questions
            WHERE user_id = ?
              AND question_id IN (
                  SELECT q.id
                  FROM exam_questions q
                  JOIN exam_papers p ON p.id = q.paper_id
                  WHERE p.source_type = 'exam'
              )
            ORDER BY last_wrong_at DESC, question_id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return _load_practice_questions_by_ids(conn, [row["question_id"] for row in rows])
    finally:
        if should_close:
            conn.close()


def retry_wrong_practice_answers(user_id: int, answers: dict) -> dict:
    _sync_question_bank_references_once()
    answer_map = {str(key): _answer_to_text(value) for key, value in (answers or {}).items()}
    question_ids = _normalize_question_ids(answer_map.keys())
    if not question_ids:
        raise ValueError("Please answer at least one wrong practice question")
    conn, should_close = _connection()
    try:
        active_ids = {
            row["question_id"]
            for row in conn.execute(
                "SELECT question_id FROM exam_practice_wrong_questions WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        }
        if not set(question_ids).issubset(active_ids):
            raise ValueError("Wrong practice questions have changed, please reload")
        questions = _load_objective_questions_by_ids(conn, question_ids)
        created_at = _now()
        items = []
        resolved_count = 0
        for question_id in question_ids:
            question = questions[question_id]
            answer_text = answer_map[str(question_id)]
            earned_score = grade_objective(
                question["question_type"], answer_text, question["correct_answer"], question["score"]
            )
            is_correct = earned_score == float(question["score"])
            if is_correct:
                conn.execute(
                    "DELETE FROM exam_practice_wrong_questions WHERE user_id = ? AND question_id = ?",
                    (user_id, question_id),
                )
                resolved_count += 1
            else:
                conn.execute(
                    """
                    UPDATE exam_practice_wrong_questions
                    SET wrong_count = wrong_count + 1,
                        last_answer_text = ?,
                        last_wrong_at = ?
                    WHERE user_id = ? AND question_id = ?
                    """,
                    (answer_text, created_at, user_id, question_id),
                )
            items.append(_practice_item(question, answer_text, is_correct, created_at, None))
        conn.commit()
        remaining_count = conn.execute(
            "SELECT COUNT(*) FROM exam_practice_wrong_questions WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
        return {
            "items": items,
            "resolved_count": resolved_count,
            "remaining_count": remaining_count,
        }
    finally:
        if should_close:
            conn.close()


def get_attempt_review(attempt_id: int) -> dict | None:
    conn, should_close = _connection()
    try:
        attempt = conn.execute(
            """
            SELECT att.id, att.user_id, att.paper_id, p.title AS paper_title,
                   att.status, att.objective_score,
                   att.suggested_subjective_score,
                   att.final_subjective_score, att.final_score,
                   att.started_at, att.submitted_at
            FROM exam_attempts att
            JOIN exam_papers p ON p.id = att.paper_id
            WHERE att.id = ?
            """,
            (attempt_id,),
        ).fetchone()
        if not attempt:
            return None

        rows = conn.execute(
            """
            SELECT q.id AS question_id, q.paper_id, q.question_type, q.order_no,
                   q.stem, q.correct_answer, q.reference_answer, q.score,
                   ans.answer_text, ans.auto_score, ans.suggested_score,
                   ans.final_score
            FROM exam_questions q
            LEFT JOIN exam_answers ans
              ON ans.question_id = q.id
             AND ans.attempt_id = ?
            WHERE q.paper_id = ?
            ORDER BY q.order_no
            """,
            (attempt_id, attempt["paper_id"]),
        ).fetchall()
        items = []
        for row in rows:
            question = dict(row)
            question["id"] = row["question_id"]
            option_rows = conn.execute(
                """
                SELECT option_key, option_text
                FROM exam_question_options
                WHERE question_id = ?
                ORDER BY option_key
                """,
                (row["question_id"],),
            ).fetchall()
            question["options"] = [
                {"key": option["option_key"], "text": option["option_text"]}
                for option in option_rows
            ]
            question = ensure_question_options(question)
            answer_text = row["answer_text"] or ""
            is_correct = None
            if row["question_type"] in OBJECTIVE_TYPES:
                is_correct = grade_objective(
                    row["question_type"],
                    answer_text,
                    row["correct_answer"],
                    row["score"],
                ) == float(row["score"])
            items.append(
                {
                    "question_id": row["question_id"],
                    "question_type": row["question_type"],
                    "order_no": row["order_no"],
                    "stem": row["stem"],
                    "options": question["options"],
                    "answer_text": answer_text,
                    "correct_answer": row["correct_answer"],
                    "reference_answer": row["reference_answer"],
                    "score": row["score"],
                    "auto_score": row["auto_score"],
                    "suggested_score": row["suggested_score"],
                    "final_score": row["final_score"],
                    "is_correct": is_correct,
                }
            )
        return {"attempt": dict(attempt), "items": items}
    finally:
        if should_close:
            conn.close()


def _normalize_answer(value: str) -> str:
    return (value or "").strip().replace(" ", "").upper()


def _normalize_option_answer(value: str) -> str:
    separators = {",", "，", "、", ";", "；", "|", "/", "\\", ".", "．", "。"}
    return "".join(char for char in _normalize_answer(value) if char not in separators)


def scale_exam_score(raw_score: float, raw_total: float, total_score: float = EXAM_TOTAL_SCORE) -> float:
    raw_total = float(raw_total or 0)
    if raw_total <= 0:
        return 0.0
    return round(float(raw_score or 0) * float(total_score) / raw_total, 4)


def _normalize_true_false_answer(value: str) -> str:
    normalized = _normalize_option_answer(value)
    truthy = {"√", "正", "正确", "对", "是", "TRUE", "T", "YES", "Y"}
    falsy = {"×", "X", "错", "错误", "否", "FALSE", "F", "NO", "N"}
    if normalized in truthy:
        return "TRUE"
    if normalized in falsy:
        return "FALSE"
    return normalized


def grade_objective(
    question_type: str,
    candidate_answer: str,
    correct_answer: str,
    score: float,
) -> float:
    if question_type == "true_false":
        candidate = _normalize_true_false_answer(candidate_answer)
        correct = _normalize_true_false_answer(correct_answer)
    else:
        candidate = _normalize_option_answer(candidate_answer)
        correct = _normalize_option_answer(correct_answer)

    if question_type == "multiple_choice":
        candidate_set = set(candidate)
        correct_set = set(correct)
        if not candidate_set or not correct_set:
            return 0.0
        if candidate_set - correct_set:
            return 0.0
        return round(float(score) * len(candidate_set) / len(correct_set), 4)

    return float(score) if candidate == correct else 0.0


def suggest_subjective_score(
    answer_text: str,
    keywords_csv: str,
    score: float,
) -> tuple[float, list[str]]:
    keywords = [item.strip() for item in (keywords_csv or "").split(",") if item.strip()]
    if not keywords:
        return 0.0, []

    hits = [keyword for keyword in keywords if keyword in answer_text]
    suggested = round(float(score) * len(hits) / len(keywords), 2)
    return suggested, hits


def _raw_paper_score_total(questions: list[dict]) -> float:
    return sum(float(question.get("score") or 0) for question in questions)


def start_attempt(user_id, paper_id, retake_eligibility_id: int | None = None) -> int:
    conn, should_close = _connection()
    try:
        active_attempt = conn.execute(
            """
            SELECT id
            FROM exam_attempts
            WHERE user_id = ? AND status = 'in_progress'
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if active_attempt:
            raise ValueError("You already have an exam in progress")
        if retake_eligibility_id is not None:
            eligibility = conn.execute(
                """
                SELECT id, user_id, paper_id, status
                FROM exam_retake_eligibilities
                WHERE id = ?
                """,
                (retake_eligibility_id,),
            ).fetchone()
            if (
                not eligibility
                or eligibility["status"] != "open"
                or int(eligibility["user_id"]) != int(user_id)
                or int(eligibility["paper_id"]) != int(paper_id)
            ):
                raise ValueError("Retake eligibility is not available")
        cursor = conn.execute(
            """
            INSERT INTO exam_attempts (
                user_id, paper_id, status, started_at, retake_eligibility_id
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, paper_id, "in_progress", _now(), retake_eligibility_id),
        )
        if retake_eligibility_id is not None:
            conn.execute(
                """
                UPDATE exam_retake_eligibilities
                SET status = 'used', used_attempt_id = ?, used_at = ?
                WHERE id = ?
                """,
                (cursor.lastrowid, _now(), retake_eligibility_id),
            )
        conn.commit()
        return cursor.lastrowid
    finally:
        if should_close:
            conn.close()


def get_active_attempt_for_user(user_id) -> dict | None:
    conn, should_close = _connection()
    try:
        row = conn.execute(
            """
            SELECT id, user_id, paper_id, status, objective_score,
                   suggested_subjective_score, final_subjective_score,
                   final_score, started_at, submitted_at, retake_eligibility_id
            FROM exam_attempts
            WHERE user_id = ? AND status = 'in_progress'
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return _dict_or_none(row)
    finally:
        if should_close:
            conn.close()


def get_attempt(attempt_id) -> dict | None:
    conn, should_close = _connection()
    try:
        row = conn.execute(
            """
            SELECT id, user_id, paper_id, status, objective_score,
                   suggested_subjective_score, final_subjective_score,
                   final_score, started_at, submitted_at, retake_eligibility_id
            FROM exam_attempts
            WHERE id = ?
            """,
            (attempt_id,),
        ).fetchone()
        return _dict_or_none(row)
    finally:
        if should_close:
            conn.close()


def submit_attempt(attempt_id, answers) -> None:
    conn, should_close = _connection()
    try:
        attempt = conn.execute(
            "SELECT id, paper_id, status FROM exam_attempts WHERE id = ?",
            (attempt_id,),
        ).fetchone()
        if not attempt or attempt["status"] != "in_progress":
            raise ValueError("考试已提交，不能重复交卷")

        objective_score = 0.0
        suggested_subjective_score = 0.0
        has_subjective = False
        answer_map = {str(key): value for key, value in (answers or {}).items()}
        questions = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, question_type, correct_answer, keywords, score
                FROM exam_questions
                WHERE paper_id = ?
                ORDER BY order_no
                """,
                (attempt["paper_id"],),
            ).fetchall()
        ]
        raw_total_score = _raw_paper_score_total(questions)

        for question in questions:
            answer_text = _answer_to_text(answer_map.get(str(question["id"]), ""))
            auto_score = 0.0
            suggested_score = 0.0
            final_score = None

            if question["question_type"] in OBJECTIVE_TYPES:
                auto_score = grade_objective(
                    question["question_type"],
                    answer_text,
                    question["correct_answer"],
                    question["score"],
                )
                final_score = auto_score
                objective_score += auto_score
            elif question["question_type"] in SUBJECTIVE_TYPES:
                suggested_score, _ = suggest_subjective_score(
                    answer_text,
                    question["keywords"],
                    question["score"],
                )
                suggested_subjective_score += suggested_score
                has_subjective = True

            conn.execute(
                """
                INSERT INTO exam_answers (
                    attempt_id, question_id, answer_text, auto_score,
                    suggested_score, final_score
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(attempt_id, question_id) DO UPDATE SET
                    answer_text = excluded.answer_text,
                    auto_score = excluded.auto_score,
                    suggested_score = excluded.suggested_score,
                    final_score = excluded.final_score
                """,
                (
                    attempt_id,
                    int(question["id"]),
                    answer_text,
                    auto_score,
                    suggested_score,
                    final_score,
                ),
            )

        status = "pending_review" if has_subjective else "completed"
        scaled_objective_score = scale_exam_score(objective_score, raw_total_score)
        scaled_suggested_subjective_score = scale_exam_score(
            suggested_subjective_score, raw_total_score
        )
        final_score = None if has_subjective else scaled_objective_score
        conn.execute(
            """
            UPDATE exam_attempts
            SET status = ?, objective_score = ?, suggested_subjective_score = ?,
                final_score = ?, submitted_at = ?
            WHERE id = ?
            """,
            (
                status,
                scaled_objective_score,
                scaled_suggested_subjective_score,
                final_score,
                _now(),
                attempt_id,
            ),
        )
        conn.commit()
    finally:
        if should_close:
            conn.close()


def list_user_attempts(user_id) -> list[dict]:
    conn, should_close = _connection()
    try:
        rows = conn.execute(
            """
            SELECT a.id, a.user_id, a.paper_id, p.title AS paper_title,
                   a.status, a.objective_score, a.suggested_subjective_score,
                   a.final_subjective_score, a.final_score, a.started_at,
                   a.submitted_at
            FROM exam_attempts a
            JOIN exam_papers p ON p.id = a.paper_id
            WHERE a.user_id = ?
            ORDER BY a.started_at DESC, a.id DESC
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if should_close:
            conn.close()


def _active_exam_takers(conn) -> list[dict]:
    roles = sorted(EXAM_TAKER_ROLES)
    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT u.id, u.username, u.real_name, r.role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE COALESCE(u.is_active, 1) = 1
              AND r.role_name IN ({_role_placeholders(roles)})
            ORDER BY r.role_name, u.real_name, u.username
            """,
            roles,
        ).fetchall()
    ]


def refresh_retake_eligibilities(conn=None) -> None:
    should_close = False
    if conn is None:
        conn, should_close = _connection()
    try:
        now = _now()
        failed_rows = conn.execute(
            """
            SELECT att.id AS attempt_id, att.user_id, att.paper_id, att.final_score,
                   p.title AS paper_title
            FROM exam_attempts att
            JOIN exam_papers p ON p.id = att.paper_id
            WHERE att.status = 'completed'
              AND COALESCE(att.final_score, 0) < ?
              AND p.source_type IN ('exam', 'formal_exam_pool')
              AND NOT EXISTS (
                  SELECT 1
                  FROM exam_attempts passed
                  WHERE passed.user_id = att.user_id
                    AND passed.paper_id = att.paper_id
                    AND passed.status = 'completed'
                    AND COALESCE(passed.final_score, 0) >= ?
              )
            """,
            (EXAM_PASSING_SCORE, EXAM_PASSING_SCORE),
        ).fetchall()
        for row in failed_rows:
            exists = conn.execute(
                """
                SELECT 1
                FROM exam_retake_eligibilities
                WHERE user_id = ?
                  AND paper_id = ?
                  AND eligibility_type = 'retake_failed'
                  AND status = 'open'
                LIMIT 1
                """,
                (row["user_id"], row["paper_id"]),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO exam_retake_eligibilities (
                    user_id, paper_id, eligibility_type, status,
                    source_attempt_id, reason, created_at
                ) VALUES (?, ?, 'retake_failed', 'open', ?, ?, ?)
                """,
                (
                    row["user_id"],
                    row["paper_id"],
                    row["attempt_id"],
                    f"Score below {EXAM_PASSING_SCORE:g}",
                    now,
                ),
            )

        current_paper = conn.execute(
            """
            SELECT p.id, p.title
            FROM exam_settings s
            JOIN exam_papers p ON p.id = CAST(s.value AS INTEGER)
            WHERE s.key = ?
              AND p.source_type = 'exam'
            """,
            ("current_exam_paper_id",),
        ).fetchone()
        if current_paper:
            for user in _active_exam_takers(conn):
                has_any_attempt = conn.execute(
                    """
                    SELECT 1
                    FROM exam_attempts
                    WHERE user_id = ?
                      AND paper_id = ?
                    LIMIT 1
                    """,
                    (user["id"], current_paper["id"]),
                ).fetchone()
                if not has_any_attempt:
                    exists = conn.execute(
                        """
                        SELECT 1
                        FROM exam_retake_eligibilities
                        WHERE user_id = ?
                          AND paper_id = ?
                          AND eligibility_type = 'makeup_absent'
                          AND status = 'open'
                        LIMIT 1
                        """,
                        (user["id"], current_paper["id"]),
                    ).fetchone()
                    if exists:
                        continue
                    conn.execute(
                        """
                        INSERT INTO exam_retake_eligibilities (
                            user_id, paper_id, eligibility_type, status,
                            reason, created_at
                        ) VALUES (?, ?, 'makeup_absent', 'open', ?, ?)
                        """,
                        (
                            user["id"],
                            current_paper["id"],
                            "No attempt record for current exam paper",
                            now,
                        ),
                    )
        if should_close:
            conn.commit()
    finally:
        if should_close:
            conn.close()


def list_retake_eligibilities(user_id: int | None = None, viewer=None) -> list[dict]:
    conn, should_close = _connection()
    try:
        refresh_retake_eligibilities(conn=conn)
        where = ["e.status = 'open'"]
        params = []
        if user_id is not None:
            where.append("e.user_id = ?")
            params.append(user_id)
        elif viewer and not can_manage_exam(viewer):
            where.append("e.user_id = ?")
            params.append(viewer.get("id"))
        rows = conn.execute(
            f"""
            SELECT e.id, e.user_id, u.username, u.real_name, r.role_name,
                   e.paper_id, p.title AS paper_title, e.eligibility_type,
                   e.status, e.source_attempt_id, e.used_attempt_id,
                   e.reason, e.created_at, e.used_at
            FROM exam_retake_eligibilities e
            JOIN users u ON u.id = e.user_id
            LEFT JOIN roles r ON r.id = u.role_id
            JOIN exam_papers p ON p.id = e.paper_id
            WHERE {" AND ".join(where)}
            ORDER BY e.eligibility_type, e.created_at DESC, e.id DESC
            """,
            params,
        ).fetchall()
        conn.commit()
        return [dict(row) for row in rows]
    finally:
        if should_close:
            conn.close()


def start_retake_attempt(user_id: int, eligibility_id: int) -> int:
    conn, should_close = _connection()
    try:
        refresh_retake_eligibilities(conn=conn)
        eligibility = conn.execute(
            """
            SELECT id, user_id, paper_id, status
            FROM exam_retake_eligibilities
            WHERE id = ?
            """,
            (eligibility_id,),
        ).fetchone()
        if not eligibility or eligibility["status"] != "open":
            raise ValueError("Retake eligibility is not available")
        if int(eligibility["user_id"]) != int(user_id):
            raise ValueError("Permission denied")
        conn.commit()
        return start_attempt(user_id, eligibility["paper_id"], eligibility_id)
    finally:
        if should_close:
            conn.close()


def list_pending_reviews() -> list[dict]:
    conn, should_close = _connection()
    try:
        rows = conn.execute(
            """
            SELECT ans.id AS answer_id, ans.attempt_id, ans.question_id,
                   ans.answer_text, ans.suggested_score, ans.final_score,
                   att.user_id, u.username, u.real_name AS user_name,
                   p.id AS paper_id, p.title AS paper_title,
                   q.question_type, q.order_no, q.stem, q.reference_answer,
                   q.keywords, q.score
            FROM exam_answers ans
            JOIN exam_attempts att ON att.id = ans.attempt_id
            JOIN users u ON u.id = att.user_id
            JOIN exam_papers p ON p.id = att.paper_id
            JOIN exam_questions q ON q.id = ans.question_id
            WHERE att.status = 'pending_review'
              AND q.question_type IN ('short_answer', 'case_analysis')
              AND ans.final_score IS NULL
            ORDER BY att.submitted_at, att.id, q.order_no
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if should_close:
            conn.close()


def review_answer(answer_id, reviewer_id, final_score, comment="") -> None:
    conn, should_close = _connection()
    try:
        answer = conn.execute(
            """
            SELECT ans.id, ans.attempt_id, ans.suggested_score
            FROM exam_answers ans
            JOIN exam_questions q ON q.id = ans.question_id
            WHERE ans.id = ?
              AND q.question_type IN ('short_answer', 'case_analysis')
            """,
            (answer_id,),
        ).fetchone()
        if not answer:
            return

        conn.execute(
            "UPDATE exam_answers SET final_score = ? WHERE id = ?",
            (final_score, answer_id),
        )
        review = conn.execute(
            "SELECT id FROM exam_subjective_reviews WHERE answer_id = ? ORDER BY id LIMIT 1",
            (answer_id,),
        ).fetchone()
        if review:
            conn.execute(
                """
                UPDATE exam_subjective_reviews
                SET reviewer_id = ?, suggested_score = ?, final_score = ?,
                    comment = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (reviewer_id, answer["suggested_score"], final_score, comment, _now(), review["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO exam_subjective_reviews (
                    answer_id, reviewer_id, suggested_score, final_score,
                    comment, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (answer_id, reviewer_id, answer["suggested_score"], final_score, comment, _now()),
            )

        remaining = conn.execute(
            """
            SELECT COUNT(*)
            FROM exam_answers ans
            JOIN exam_questions q ON q.id = ans.question_id
            WHERE ans.attempt_id = ?
              AND q.question_type IN ('short_answer', 'case_analysis')
              AND ans.final_score IS NULL
            """,
            (answer["attempt_id"],),
        ).fetchone()[0]
        if remaining == 0:
            totals = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN q.question_type IN ('short_answer', 'case_analysis') THEN ans.final_score ELSE 0 END), 0) AS subjective,
                    COALESCE(SUM(CASE WHEN q.question_type IN ('single_choice', 'multiple_choice', 'true_false') THEN ans.final_score ELSE 0 END), 0) AS objective,
                    COALESCE(SUM(q.score), 0) AS raw_total
                FROM exam_answers ans
                JOIN exam_questions q ON q.id = ans.question_id
                WHERE ans.attempt_id = ?
                """,
                (answer["attempt_id"],),
            ).fetchone()
            raw_total = float(totals["raw_total"] or 0)
            final_subjective_score = scale_exam_score(totals["subjective"], raw_total)
            objective_score = scale_exam_score(totals["objective"], raw_total)
            final_score_total = scale_exam_score(
                float(totals["objective"] or 0) + float(totals["subjective"] or 0),
                raw_total,
            )
            conn.execute(
                """
                UPDATE exam_attempts
                SET status = 'completed',
                    objective_score = ?,
                    final_subjective_score = ?,
                    final_score = ?
                WHERE id = ?
                """,
                (objective_score, final_subjective_score, final_score_total, answer["attempt_id"]),
            )
        conn.commit()
    finally:
        if should_close:
            conn.close()


def delete_exam_attempt(attempt_id: int) -> None:
    conn, should_close = _connection()
    try:
        attempt = conn.execute(
            "SELECT id FROM exam_attempts WHERE id = ?",
            (attempt_id,),
        ).fetchone()
        if not attempt:
            raise ValueError("Exam attempt not found")
        # A deleted retake attempt releases its eligibility for another attempt.
        conn.execute(
            """
            UPDATE exam_retake_eligibilities
            SET status = 'open', used_attempt_id = NULL, used_at = NULL
            WHERE used_attempt_id = ?
            """,
            (attempt_id,),
        )
        # A source attempt may be removed after its retake has been used. Keep
        # that retake, but detach the now-deleted source attempt. Unused
        # eligibility has no purpose without its source and is removed.
        conn.execute(
            """
            UPDATE exam_retake_eligibilities
            SET source_attempt_id = NULL
            WHERE source_attempt_id = ? AND used_attempt_id IS NOT NULL
            """,
            (attempt_id,),
        )
        conn.execute(
            """
            DELETE FROM exam_retake_eligibilities
            WHERE source_attempt_id = ? AND used_attempt_id IS NULL
            """,
            (attempt_id,),
        )
        conn.execute(
            """
            DELETE FROM exam_subjective_reviews
            WHERE answer_id IN (
                SELECT id FROM exam_answers WHERE attempt_id = ?
            )
            """,
            (attempt_id,),
        )
        conn.execute("DELETE FROM exam_answers WHERE attempt_id = ?", (attempt_id,))
        conn.execute("DELETE FROM exam_attempts WHERE id = ?", (attempt_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if should_close:
            conn.close()


def list_results(filters=None) -> list[dict]:
    filters = filters or {}
    viewer = filters.get("viewer")
    where = []
    params = []

    if viewer and not can_manage_exam(viewer):
        where.append("att.user_id = ?")
        params.append(viewer.get("id"))
    if filters.get("paper_id"):
        where.append("att.paper_id = ?")
        params.append(filters["paper_id"])
    if filters.get("status"):
        where.append("att.status = ?")
        params.append(filters["status"])
    if filters.get("keyword"):
        where.append("(u.real_name LIKE ? OR u.username LIKE ? OR p.title LIKE ?)")
        keyword = f"%{filters['keyword']}%"
        params.extend([keyword, keyword, keyword])

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    conn, should_close = _connection()
    try:
        rows = conn.execute(
            f"""
            WITH ranked_results AS (
                SELECT att.id, att.id AS attempt_id, att.user_id,
                       u.real_name AS user_name, u.username, r.role_name,
                       att.paper_id, p.title AS paper_title, att.status,
                       att.objective_score, att.suggested_subjective_score,
                       att.final_subjective_score, att.final_score,
                       att.started_at, att.submitted_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY att.user_id
                           ORDER BY
                               CASE WHEN att.final_score IS NULL THEN 1 ELSE 0 END,
                               att.final_score DESC,
                               COALESCE(att.submitted_at, att.started_at) DESC,
                               att.id DESC
                       ) AS result_rank
                FROM exam_attempts att
                JOIN users u ON u.id = att.user_id
                LEFT JOIN roles r ON r.id = u.role_id
                JOIN exam_papers p ON p.id = att.paper_id
                {where_sql}
            )
            SELECT id, attempt_id, user_id, user_name, username, role_name,
                   paper_id, paper_title, status, objective_score,
                   suggested_subjective_score, final_subjective_score, final_score,
                   started_at, submitted_at
            FROM ranked_results
            WHERE result_rank = 1
            ORDER BY COALESCE(submitted_at, started_at) DESC, attempt_id DESC
            """,
            params,
        ).fetchall()
        results = [dict(row) for row in rows]
        if viewer and can_manage_exam(viewer) and not filters.get("paper_id") and not filters.get("status"):
            listed_user_ids = {row["user_id"] for row in results}
            material_clerks = conn.execute(
                """
                SELECT u.id AS user_id, u.real_name AS user_name, u.username, r.role_name
                FROM users u JOIN roles r ON r.id = u.role_id
                WHERE r.role_name = '材料员' AND COALESCE(u.is_active, 1) = 1
                ORDER BY u.id
                """
            ).fetchall()
            for clerk in material_clerks:
                if clerk["user_id"] not in listed_user_ids:
                    results.append({
                        "id": None, "attempt_id": None, "user_id": clerk["user_id"],
                        "user_name": clerk["user_name"], "username": clerk["username"],
                        "role_name": clerk["role_name"], "paper_id": None, "paper_title": "-",
                        "status": "not_completed", "objective_score": None,
                        "suggested_subjective_score": None, "final_subjective_score": None,
                        "final_score": None, "started_at": None, "submitted_at": None,
                    })
            results.sort(key=lambda row: row.get("status") != "not_completed")
        return results
    finally:
        if should_close:
            conn.close()
