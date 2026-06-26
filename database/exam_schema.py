"""Exam center database schema."""


def init_exam_schema(conn):
    cursor = conn.cursor()
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS exam_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL DEFAULT 60,
            total_score INTEGER NOT NULL DEFAULT 100,
            source_type TEXT NOT NULL DEFAULT 'exam',
            create_time TEXT
        );

        CREATE TABLE IF NOT EXISTS exam_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

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
        );

        CREATE TABLE IF NOT EXISTS exam_question_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            option_key TEXT NOT NULL,
            option_text TEXT NOT NULL,
            FOREIGN KEY (question_id) REFERENCES exam_questions(id) ON DELETE CASCADE
        );

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
        );

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
        );

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
        );

        CREATE TABLE IF NOT EXISTS exam_practice_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            answer_text TEXT NOT NULL,
            is_correct INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (question_id) REFERENCES exam_questions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_exam_attempts_user ON exam_attempts(user_id);
        CREATE INDEX IF NOT EXISTS idx_exam_attempts_paper ON exam_attempts(paper_id);
        CREATE INDEX IF NOT EXISTS idx_exam_questions_paper ON exam_questions(paper_id);
        CREATE INDEX IF NOT EXISTS idx_exam_options_question ON exam_question_options(question_id);
        CREATE INDEX IF NOT EXISTS idx_exam_answers_attempt ON exam_answers(attempt_id);
        CREATE INDEX IF NOT EXISTS idx_exam_reviews_answer ON exam_subjective_reviews(answer_id);
        CREATE INDEX IF NOT EXISTS idx_exam_practice_user ON exam_practice_attempts(user_id);
        """
    )
    conn.commit()
