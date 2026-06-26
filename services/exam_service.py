"""Exam center query and grading helpers."""

from __future__ import annotations

from datetime import datetime


OBJECTIVE_TYPES = {"single_choice", "multiple_choice", "true_false"}
SUBJECTIVE_TYPES = {"short_answer", "case_analysis"}
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


def _answer_to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(item) for item in value)
    return str(value)


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
            ORDER BY id
            """
        ).fetchall()
        return [dict(row) for row in rows]
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

        return questions
    finally:
        if should_close:
            conn.close()


def get_random_practice_questions(limit=10, paper_id=None) -> list[dict]:
    conn, should_close = _connection()
    try:
        params = []
        where = ""
        if paper_id is not None:
            where = "WHERE q.paper_id = ?"
            params.append(paper_id)
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
        return questions
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
        return float(score) if set(candidate) == set(correct) and len(candidate) == len(correct) else 0.0

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
            "SELECT id, paper_id FROM exam_attempts WHERE id = ?",
            (attempt_id,),
        ).fetchone()
        if not attempt:
            return

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
