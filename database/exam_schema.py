"""Exam center database schema."""


def init_exam_schema(conn):
    cursor = conn.cursor()
    table_statements = [
        """
        CREATE TABLE IF NOT EXISTS exam_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL DEFAULT 60,
            total_score INTEGER NOT NULL DEFAULT 100,
            source_type TEXT NOT NULL DEFAULT 'exam',
            create_time TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exam_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exam_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER NOT NULL,
            question_type TEXT NOT NULL,
            order_no INTEGER NOT NULL,
            stem TEXT NOT NULL,
            correct_answer TEXT,
            reference_answer TEXT,
            keywords TEXT,
            score INTEGER NOT NULL,
            FOREIGN KEY (paper_id) REFERENCES exam_papers(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exam_question_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            option_key TEXT NOT NULL,
            option_text TEXT NOT NULL,
            FOREIGN KEY (question_id) REFERENCES exam_questions(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exam_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            paper_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('in_progress', 'pending_review', 'completed')),
            objective_score REAL NOT NULL DEFAULT 0,
            suggested_subjective_score REAL NOT NULL DEFAULT 0,
            final_subjective_score REAL,
            final_score REAL,
            started_at TEXT NOT NULL,
            submitted_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (paper_id) REFERENCES exam_papers(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exam_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            answer_text TEXT NOT NULL DEFAULT '',
            auto_score REAL NOT NULL DEFAULT 0,
            suggested_score REAL NOT NULL DEFAULT 0,
            final_score REAL,
            UNIQUE (attempt_id, question_id),
            FOREIGN KEY (attempt_id) REFERENCES exam_attempts(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES exam_questions(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exam_subjective_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            answer_id INTEGER NOT NULL,
            reviewer_id INTEGER NOT NULL,
            suggested_score REAL NOT NULL,
            final_score REAL NOT NULL,
            comment TEXT,
            reviewed_at TEXT NOT NULL,
            FOREIGN KEY (answer_id) REFERENCES exam_answers(id) ON DELETE CASCADE,
            FOREIGN KEY (reviewer_id) REFERENCES users(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exam_practice_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            answer_text TEXT NOT NULL,
            is_correct INTEGER,
            accuracy_credit REAL DEFAULT 0,
            created_at TEXT NOT NULL,
            practice_session_id TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (question_id) REFERENCES exam_questions(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exam_practice_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            question_ids TEXT NOT NULL DEFAULT '[]',
            answers_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exam_practice_wrong_questions (
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            wrong_count INTEGER NOT NULL DEFAULT 1,
            last_answer_text TEXT NOT NULL DEFAULT '',
            first_wrong_at TEXT NOT NULL,
            last_wrong_at TEXT NOT NULL,
            PRIMARY KEY (user_id, question_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (question_id) REFERENCES exam_questions(id)
        )
        """,
    ]
    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_exam_attempts_user ON exam_attempts(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_exam_attempts_paper ON exam_attempts(paper_id)",
        "CREATE INDEX IF NOT EXISTS idx_exam_questions_paper ON exam_questions(paper_id)",
        "CREATE INDEX IF NOT EXISTS idx_exam_options_question ON exam_question_options(question_id)",
        "CREATE INDEX IF NOT EXISTS idx_exam_answers_attempt ON exam_answers(attempt_id)",
        "CREATE INDEX IF NOT EXISTS idx_exam_reviews_answer ON exam_subjective_reviews(answer_id)",
        "CREATE INDEX IF NOT EXISTS idx_exam_practice_user ON exam_practice_attempts(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_exam_practice_session ON exam_practice_attempts(user_id, practice_session_id)",
        "CREATE INDEX IF NOT EXISTS idx_exam_practice_drafts_user ON exam_practice_drafts(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_exam_practice_wrong_questions_user ON exam_practice_wrong_questions(user_id, last_wrong_at DESC)",
    ]

    for statement in table_statements:
        cursor.execute(statement)

    practice_columns = {
        row[1]
        for row in cursor.execute("PRAGMA table_info(exam_practice_attempts)")
    }
    if "practice_session_id" not in practice_columns:
        cursor.execute(
            "ALTER TABLE exam_practice_attempts ADD COLUMN practice_session_id TEXT"
        )
    if "accuracy_credit" not in practice_columns:
        cursor.execute(
            "ALTER TABLE exam_practice_attempts ADD COLUMN accuracy_credit REAL DEFAULT 0"
        )
        cursor.execute(
            """
            UPDATE exam_practice_attempts
            SET accuracy_credit = CASE WHEN is_correct = 1 THEN 1 ELSE 0 END
            WHERE accuracy_credit IS NULL OR accuracy_credit = 0
            """
        )

    _require_manual_current_exam_selection(cursor)

    draft_columns = {
        row[1]
        for row in cursor.execute("PRAGMA table_info(exam_practice_drafts)")
    }
    if "question_ids" not in draft_columns:
        cursor.execute(
            "ALTER TABLE exam_practice_drafts ADD COLUMN question_ids TEXT NOT NULL DEFAULT '[]'"
        )
    if "answers_json" not in draft_columns:
        cursor.execute(
            "ALTER TABLE exam_practice_drafts ADD COLUMN answers_json TEXT NOT NULL DEFAULT '{}'"
        )
    if "updated_at" not in draft_columns:
        cursor.execute(
            "ALTER TABLE exam_practice_drafts ADD COLUMN updated_at TEXT"
        )

    _backfill_active_wrong_practice_questions(cursor)

    for statement in index_statements:
        cursor.execute(statement)


def _require_manual_current_exam_selection(cursor):
    migration_key = "manual_current_exam_required_migration_20260711"
    migrated = cursor.execute(
        "SELECT value FROM exam_settings WHERE key = ?",
        (migration_key,),
    ).fetchone()
    if migrated:
        return

    cursor.execute(
        "DELETE FROM exam_settings WHERE key = ?",
        ("current_exam_paper_id",),
    )
    cursor.execute(
        "INSERT INTO exam_settings (key, value) VALUES (?, ?)",
        (migration_key, "done"),
    )


def _backfill_active_wrong_practice_questions(cursor):
    migration_key = "wrong_practice_questions_backfill_20260713"
    migrated = cursor.execute(
        "SELECT value FROM exam_settings WHERE key = ?",
        (migration_key,),
    ).fetchone()
    if migrated:
        return

    cursor.execute(
        """
        INSERT OR IGNORE INTO exam_practice_wrong_questions (
            user_id, question_id, wrong_count, last_answer_text,
            first_wrong_at, last_wrong_at
        )
        SELECT pa.user_id,
               pa.question_id,
               COUNT(*) AS wrong_count,
               (
                   SELECT latest.answer_text
                   FROM exam_practice_attempts latest
                   WHERE latest.user_id = pa.user_id
                     AND latest.question_id = pa.question_id
                     AND latest.is_correct = 0
                   ORDER BY latest.created_at DESC, latest.id DESC
                   LIMIT 1
               ) AS last_answer_text,
               MIN(pa.created_at) AS first_wrong_at,
               MAX(pa.created_at) AS last_wrong_at
        FROM exam_practice_attempts pa
        WHERE pa.is_correct = 0
          AND NOT EXISTS (
              SELECT 1
              FROM exam_practice_attempts later_correct
              WHERE later_correct.user_id = pa.user_id
                AND later_correct.question_id = pa.question_id
                AND later_correct.is_correct = 1
                AND (
                    later_correct.created_at > pa.created_at
                    OR (
                        later_correct.created_at = pa.created_at
                        AND later_correct.id > pa.id
                    )
                )
          )
        GROUP BY pa.user_id, pa.question_id
        """
    )
    cursor.execute(
        "INSERT INTO exam_settings (key, value) VALUES (?, ?)",
        (migration_key, "done"),
    )
