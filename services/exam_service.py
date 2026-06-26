"""Exam center query and grading helpers."""

from __future__ import annotations


OBJECTIVE_TYPES = {"single_choice", "multiple_choice", "true_false"}
SUBJECTIVE_TYPES = {"short_answer", "case_analysis"}


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
