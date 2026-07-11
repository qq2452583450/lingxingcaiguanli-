"""Exam center query and grading helpers."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4


OBJECTIVE_TYPES = {"single_choice", "multiple_choice", "true_false"}
SUBJECTIVE_TYPES = {"short_answer", "case_analysis"}
DAILY_PRACTICE_QUESTION_COUNT = 30
DAILY_PRACTICE_REQUIRED_ACCURACY = 0.8
DAILY_PRACTICE_PAPER_TITLES = {
    "第一套（新编实操版）",
    "第二套（新编案例版）",
    "第三套（新编内控版）",
    "第四套（新编实操易错版）",
    "第五套（新编综合押题版）",
}
EXAM_TAKER_ROLES = {"材料员", "材料审批负责人", "基地负责人"}
EXAM_MANAGER_ROLES = {"系统管理员", "材料审批负责人"}


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


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today_prefix() -> str:
    return datetime.now().strftime("%Y-%m-%d")


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
        if paper_id is not None:
            where_parts.append("q.paper_id = ?")
            params.append(paper_id)
        where_parts.append("p.source_type = 'exam'")
        where_parts.append(f"p.title IN ({title_placeholders})")
        params.extend(sorted(DAILY_PRACTICE_PAPER_TITLES))
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
        "reference_answer": question.get("reference_answer"),
        "is_correct": bool(is_correct),
        "accuracy_credit": credit,
        "score": question["score"],
        "created_at": created_at,
    }


def record_practice_answers(user_id: int, answers: dict) -> dict:
    answer_map = {str(key): _answer_to_text(value) for key, value in (answers or {}).items()}
    question_ids = [int(question_id) for question_id in answer_map.keys()]
    conn, should_close = _connection()
    try:
        questions = _load_objective_questions_by_ids(conn, question_ids)
        session_id = uuid4().hex
        created_at = _now()
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
            items.append(_practice_item(question, answer_text, is_correct, created_at, session_id, accuracy_credit))
        total_count = len(items)
        correct_count = sum(1 for item in items if item["is_correct"])
        accuracy_credit = sum(float(item["accuracy_credit"]) for item in items)
        accuracy = round(accuracy_credit / total_count, 4) if total_count else 0.0
        passed = (
            total_count >= DAILY_PRACTICE_QUESTION_COUNT
            and accuracy >= DAILY_PRACTICE_REQUIRED_ACCURACY
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
            "daily_status": get_daily_practice_status(user_id, conn=conn),
        }
    finally:
        if should_close:
            conn.close()


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
        users = conn.execute(
            """
            SELECT u.id, u.username, u.real_name, r.role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE COALESCE(u.is_active, 1) = 1
              AND r.role_name IN ('材料员', '材料审批负责人', '基地负责人')
            ORDER BY r.role_name, u.real_name, u.username
            """
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


def _practice_history_rows(user_id: int, only_wrong: bool, limit: int) -> list[dict]:
    where_wrong = "AND pa.is_correct = 0" if only_wrong else ""
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
              {where_wrong}
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
    return _practice_history_rows(user_id, only_wrong=False, limit=limit)


def list_wrong_practice_questions(user_id: int, limit: int = 100) -> list[dict]:
    return _practice_history_rows(user_id, only_wrong=True, limit=limit)


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


def grade_objective(
    question_type: str,
    candidate_answer: str,
    correct_answer: str,
    score: float,
) -> float:
    candidate = _normalize_answer(candidate_answer)
    correct = _normalize_answer(correct_answer)

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


def start_attempt(user_id, paper_id) -> int:
    conn, should_close = _connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO exam_attempts (user_id, paper_id, status, started_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, paper_id, "in_progress", _now()),
        )
        conn.commit()
        return cursor.lastrowid
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
                   final_score, started_at, submitted_at
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
        final_score = None if has_subjective else objective_score
        conn.execute(
            """
            UPDATE exam_attempts
            SET status = ?, objective_score = ?, suggested_subjective_score = ?,
                final_score = ?, submitted_at = ?
            WHERE id = ?
            """,
            (
                status,
                objective_score,
                suggested_subjective_score,
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
                    COALESCE(SUM(CASE WHEN q.question_type IN ('single_choice', 'multiple_choice', 'true_false') THEN ans.final_score ELSE 0 END), 0) AS objective
                FROM exam_answers ans
                JOIN exam_questions q ON q.id = ans.question_id
                WHERE ans.attempt_id = ?
                """,
                (answer["attempt_id"],),
            ).fetchone()
            final_subjective_score = float(totals["subjective"])
            final_score_total = float(totals["objective"]) + final_subjective_score
            conn.execute(
                """
                UPDATE exam_attempts
                SET status = 'completed',
                    final_subjective_score = ?,
                    final_score = ?
                WHERE id = ?
                """,
                (final_subjective_score, final_score_total, answer["attempt_id"]),
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
            SELECT att.id, att.id AS attempt_id, att.user_id, u.real_name AS user_name, u.username,
                   r.role_name, att.paper_id, p.title AS paper_title,
                   att.status, att.objective_score,
                   att.suggested_subjective_score,
                   att.final_subjective_score, att.final_score,
                   att.started_at, att.submitted_at
            FROM exam_attempts att
            JOIN users u ON u.id = att.user_id
            LEFT JOIN roles r ON r.id = u.role_id
            JOIN exam_papers p ON p.id = att.paper_id
            {where_sql}
            ORDER BY att.started_at DESC, att.id DESC
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if should_close:
            conn.close()
