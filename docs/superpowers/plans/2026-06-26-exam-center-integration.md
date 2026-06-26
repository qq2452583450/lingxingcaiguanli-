# Exam Center Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the existing `kaoshi` exam system into the zero-material management system as an "考试中心" module that uses the existing internal `users` login session.

**Architecture:** Add exam-specific database tables with an `exam_` prefix inside the existing SQLite database, then expose exam behavior through a new Flask blueprint under `/api/exam`. Port the stable exam parser, grading logic, and service behavior from `C:\Users\24525\Desktop\CODEX\kaoshi`, but replace all exam-local users with zero-material `session['user']` and `users.id`.

**Tech Stack:** Flask blueprints, SQLite, pytest, vanilla JavaScript single-page UI in `index.html` and `static/js/app.js`, `python-docx` for Word import.

---

## File Structure

Create:

- `database/exam_schema.py`: owns idempotent creation of `exam_` tables and indexes.
- `services/exam_import_service.py`: ports Word parsing from `kaoshi/exam_system/docx_importer.py` and imports papers/questions into `exam_` tables.
- `services/exam_service.py`: owns permissions, paper listing, random practice, attempt lifecycle, grading, review, and result queries.
- `blueprints/exam.py`: exposes JSON APIs under `/api/exam`.
- `static/js/exam.js`: owns front-end state and rendering for the exam center.
- `tests/test_exam_schema.py`: verifies database tables and initialization.
- `tests/test_exam_service.py`: verifies service behavior and permissions.
- `tests/test_exam_api.py`: verifies logged-in API behavior.
- `tests/test_frontend_exam.py`: verifies front-end module presence and role labels.

Modify:

- `app.py`: register `exam_bp`.
- `blueprints/__init__.py`: export `exam_bp`.
- `database/init_db.py`: call `init_exam_schema(conn)` during database initialization.
- `database/auto_fix.py`: call `init_exam_schema(conn)` during schema repair.
- `tests/conftest.py`: initialize exam schema in `test_db` and register `exam_bp`.
- `requirements.txt`: keep `python-docx` available if not already present.
- `index.html`: add the "考试中心" nav item and module markup.
- `static/js/app.js`: load `static/js/exam.js`, route `showModule('exam')`, and apply role visibility.
- `static/css/style.css`: add compact exam UI styles that follow existing system styling.

Source assets:

- Copy current exam source `.docx` files from `C:\Users\24525\Desktop\CODEX\kaoshi` into `docs/exam_sources/`. Use the receiving-standard file as the formal paper source and the question-bank file as the practice bank source.

## Task 1: Database Schema

**Files:**
- Create: `database/exam_schema.py`
- Modify: `database/init_db.py`
- Modify: `database/auto_fix.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_exam_schema.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/test_exam_schema.py`:

```python
import sqlite3


def table_names(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def test_exam_schema_creates_required_tables(test_db):
    conn = sqlite3.connect(test_db)
    names = table_names(conn)

    assert {
        "exam_papers",
        "exam_questions",
        "exam_question_options",
        "exam_attempts",
        "exam_answers",
        "exam_subjective_reviews",
        "exam_practice_attempts",
        "exam_settings",
    }.issubset(names)


def test_exam_attempts_reference_existing_users(test_db):
    conn = sqlite3.connect(test_db)
    columns = {row[1]: row for row in conn.execute("PRAGMA table_info(exam_attempts)")}

    assert columns["user_id"][2].upper() == "INTEGER"
    assert columns["paper_id"][2].upper() == "INTEGER"
    assert columns["status"][2].upper() == "TEXT"
```

- [ ] **Step 2: Run schema tests to verify they fail**

Run:

```powershell
& 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_exam_schema.py -q
```

Expected: failure because `exam_` tables do not exist.

- [ ] **Step 3: Add exam schema initializer**

Create `database/exam_schema.py`:

```python
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
        """
    )
    conn.commit()
```

- [ ] **Step 4: Wire schema into app initialization**

In `database/init_db.py`, import and call the initializer:

```python
from database.exam_schema import init_exam_schema
```

Inside `init_database()`, after the existing `roles` table creation and before `conn.commit()`:

```python
    init_exam_schema(conn)
```

In `database/auto_fix.py`, import and call after `conn = sqlite3.connect(...)`:

```python
from database.exam_schema import init_exam_schema

init_exam_schema(conn)
```

In `tests/conftest.py`, after the base user/role tables are created:

```python
    from database.exam_schema import init_exam_schema
    init_exam_schema(conn)
```

- [ ] **Step 5: Run schema tests and related database tests**

Run:

```powershell
& 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_exam_schema.py tests/test_api.py::TestAuthAPI::test_login_success -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add database/exam_schema.py database/init_db.py database/auto_fix.py tests/conftest.py tests/test_exam_schema.py
git commit -m "Add exam center schema"
```

## Task 2: Import and Grading Core

**Files:**
- Create: `services/exam_import_service.py`
- Create or Modify: `services/exam_service.py`
- Copy source assets into: `docs/exam_sources/`
- Test: `tests/test_exam_import_service.py`

- [ ] **Step 1: Write failing import tests**

Create `tests/test_exam_import_service.py`:

```python
from pathlib import Path

from services.exam_import_service import parse_exam_docx, import_exam_papers_from_docx
from services.exam_service import list_papers, get_paper_questions, get_current_exam_paper


def source_docx():
    return next(Path("docs/exam_sources").glob("*材料进场验收标准专项考试卷*.docx"))


def test_parse_receiving_exam_docx_has_five_complete_papers():
    papers = parse_exam_docx(source_docx())

    assert [paper["title"] for paper in papers] == [
        "第一套（新编实操版）",
        "第二套（新编案例版）",
        "第三套（新编内控版）",
        "第四套（新编实操易错版）",
        "第五套（新编综合押题版）",
    ]
    assert all(len(paper["questions"]) == 38 for paper in papers)


def test_import_exam_papers_sets_current_exam_paper(test_db):
    result = import_exam_papers_from_docx(source_docx())

    papers = list_papers()
    current = get_current_exam_paper()

    assert result == {"inserted": 5, "removed": 0}
    assert len(papers) == 5
    assert current["title"] == "第一套（新编实操版）"
    assert len(get_paper_questions(current["id"])) == 38
```

- [ ] **Step 2: Copy the source Word files**

Run:

```powershell
New-Item -ItemType Directory -Force -Path .\docs\exam_sources
Copy-Item -LiteralPath 'C:\Users\24525\Desktop\CODEX\kaoshi\中天建设项目仓管、收料岗-材料进场验收标准专项考试卷（全新5套完整版）(3).docx' -Destination .\docs\exam_sources\
Copy-Item -LiteralPath 'C:\Users\24525\Desktop\CODEX\kaoshi\项目物资管理岗位考核题库.docx' -Destination .\docs\exam_sources\
```

- [ ] **Step 3: Run import tests to verify they fail**

Run:

```powershell
& 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_exam_import_service.py -q
```

Expected: failure because `services.exam_import_service` and `services.exam_service` are not implemented.

- [ ] **Step 4: Port parser and grading helpers**

Create `services/exam_import_service.py` by porting these stable functions from `C:\Users\24525\Desktop\CODEX\kaoshi\exam_system\docx_importer.py`:

```python
parse_docx as parse_exam_docx
parse_question_bank_docx
```

Keep the parser output dictionaries unchanged:

```python
{
    "title": "第一套（新编实操版）",
    "duration_minutes": 60,
    "total_score": 100,
    "questions": [
        {
            "question_type": "single_choice",
            "order_no": 1,
            "stem": "...",
            "options": [{"key": "A", "text": "..."}],
            "correct_answer": "B",
            "reference_answer": "",
            "keywords": "",
            "score": 2,
        }
    ],
}
```

In `services/exam_service.py`, port grading logic from `kaoshi/exam_system/grading.py`:

```python
OBJECTIVE_TYPES = {"single_choice", "multiple_choice", "true_false"}
SUBJECTIVE_TYPES = {"short_answer", "case_analysis"}


def grade_objective(question, answer_text):
    if question["question_type"] == "multiple_choice":
        return question["score"] if set(answer_text) == set(question["correct_answer"]) else 0
    return question["score"] if answer_text == question["correct_answer"] else 0


def suggest_subjective_score(question, answer_text):
    keywords = [item.strip() for item in (question.get("keywords") or "").split(",") if item.strip()]
    if not keywords:
        return 0
    matched = sum(1 for keyword in keywords if keyword in answer_text)
    return round(question["score"] * matched / len(keywords), 1)
```

- [ ] **Step 5: Implement import persistence**

In `services/exam_import_service.py`, add:

```python
from pathlib import Path

from helpers import get_now
from helpers.db_helper import get_db


def import_exam_papers_from_docx(path):
    papers = parse_exam_docx(Path(path))
    conn = get_db()
    cursor = conn.cursor()
    existing = cursor.execute("SELECT id FROM exam_papers WHERE source_type = 'exam'").fetchall()
    removed = len(existing)
    cursor.execute("DELETE FROM exam_papers WHERE source_type = 'exam'")

    first_paper_id = None
    for paper in papers:
        paper_id = insert_paper(cursor, paper, source_type="exam")
        if first_paper_id is None:
            first_paper_id = paper_id

    if first_paper_id:
        cursor.execute(
            """
            INSERT INTO exam_settings (key, value)
            VALUES ('current_exam_paper_id', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(first_paper_id),),
        )
    conn.commit()
    return {"inserted": len(papers), "removed": removed}


def insert_paper(cursor, paper, source_type="exam"):
    cursor.execute(
        "INSERT INTO exam_papers (title, duration_minutes, total_score, source_type, create_time) VALUES (?, ?, ?, ?, ?)",
        (paper["title"], paper["duration_minutes"], paper["total_score"], source_type, get_now()),
    )
    paper_id = cursor.lastrowid
    for question in paper["questions"]:
        cursor.execute(
            """
            INSERT INTO exam_questions
            (paper_id, question_type, order_no, stem, correct_answer, reference_answer, keywords, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper_id,
                question["question_type"],
                question["order_no"],
                question["stem"],
                question.get("correct_answer", ""),
                question.get("reference_answer", ""),
                question.get("keywords", ""),
                question["score"],
            ),
        )
        question_id = cursor.lastrowid
        for option in question.get("options", []):
            cursor.execute(
                "INSERT INTO exam_question_options (question_id, option_key, option_text) VALUES (?, ?, ?)",
                (question_id, option["key"], option["text"]),
            )
    return paper_id
```

- [ ] **Step 6: Implement minimal paper service**

In `services/exam_service.py`, add:

```python
from helpers.db_helper import get_db


def _dict(row):
    return dict(row) if row is not None else None


def list_papers():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM exam_papers
        ORDER BY CASE WHEN source_type = 'bank' THEN 1 ELSE 0 END, id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_current_exam_paper():
    conn = get_db()
    setting = conn.execute("SELECT value FROM exam_settings WHERE key = 'current_exam_paper_id'").fetchone()
    if not setting:
        return None
    return _dict(conn.execute("SELECT * FROM exam_papers WHERE id = ?", (setting["value"],)).fetchone())


def get_paper_questions(paper_id):
    conn = get_db()
    questions = []
    for row in conn.execute("SELECT * FROM exam_questions WHERE paper_id = ? ORDER BY order_no", (paper_id,)).fetchall():
        question = dict(row)
        option_rows = conn.execute(
            "SELECT option_key, option_text FROM exam_question_options WHERE question_id = ? ORDER BY option_key",
            (question["id"],),
        ).fetchall()
        question["options"] = [{"key": opt["option_key"], "text": opt["option_text"]} for opt in option_rows]
        questions.append(question)
    return questions
```

- [ ] **Step 7: Run import tests**

Run:

```powershell
& 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_exam_import_service.py -q
```

Expected: all import tests pass.

- [ ] **Step 8: Commit**

```powershell
git add docs/exam_sources services/exam_import_service.py services/exam_service.py tests/test_exam_import_service.py
git commit -m "Import exam papers into zero-material database"
```

## Task 3: Service Permissions and Exam Lifecycle

**Files:**
- Modify: `services/exam_service.py`
- Test: `tests/test_exam_service.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/test_exam_service.py`:

```python
import sqlite3

from services.exam_import_service import import_exam_papers_from_docx
from services.exam_service import (
    can_take_exam,
    can_manage_exam,
    get_random_practice_questions,
    start_attempt,
    submit_attempt,
    get_attempt,
    list_user_attempts,
    list_results,
    list_pending_reviews,
    review_answer,
)


def create_user(test_db, role_name, username="user1", real_name="用户"):
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO roles (role_name, permissions) VALUES (?, '')", (role_name,))
    role_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO users (username, password, real_name, role_id, is_active, create_time) VALUES (?, 'x', ?, ?, 1, '2026-06-26')",
        (username, real_name, role_id),
    )
    user_id = cursor.lastrowid
    conn.commit()
    return {"id": user_id, "username": username, "real_name": real_name, "role_name": role_name}


def seed_exam_data():
    import_exam_papers_from_docx("docs/exam_sources/中天建设项目仓管、收料岗-材料进场验收标准专项考试卷（全新5套完整版）(3).docx")


def test_exam_permissions_match_internal_roles(test_db):
    assert can_take_exam({"role_name": "材料员"}) is True
    assert can_take_exam({"role_name": "材料审批负责人"}) is True
    assert can_take_exam({"role_name": "基地负责人"}) is True
    assert can_take_exam({"role_name": "供应商"}) is False

    assert can_manage_exam({"role_name": "系统管理员"}) is True
    assert can_manage_exam({"role_name": "材料审批负责人"}) is True
    assert can_manage_exam({"role_name": "材料员"}) is False


def test_submit_attempt_scores_objective_and_waits_for_review(test_db):
    user = create_user(test_db, "材料员")
    seed_exam_data()
    questions = get_random_practice_questions(limit=2)
    paper_id = questions[0]["paper_id"]
    attempt_id = start_attempt(user["id"], paper_id)
    paper_questions = get_random_practice_questions(limit=38, paper_id=paper_id)
    answers = {str(q["id"]): q["correct_answer"] for q in paper_questions if q["question_type"] in {"single_choice", "multiple_choice", "true_false"}}

    submit_attempt(attempt_id, answers)
    attempt = get_attempt(attempt_id)

    assert attempt["status"] in {"pending_review", "completed"}
    assert attempt["objective_score"] > 0
    assert len(list_user_attempts(user["id"])) == 1


def test_manager_can_review_subjective_answer_and_see_all_results(test_db):
    user = create_user(test_db, "材料员", "clerk", "材料员")
    manager = create_user(test_db, "材料审批负责人", "manager", "审批负责人")
    seed_exam_data()
    paper_questions = get_random_practice_questions(limit=38)
    paper_id = paper_questions[0]["paper_id"]
    attempt_id = start_attempt(user["id"], paper_id)
    answers = {str(q["id"]): q.get("correct_answer", "") for q in paper_questions}

    submit_attempt(attempt_id, answers)
    pending = list_pending_reviews()
    if pending:
        review_answer(pending[0]["answer_id"], manager["id"], pending[0]["score"], "通过")

    assert len(list_results({"viewer": manager})) >= 1
```

- [ ] **Step 2: Run service tests to verify they fail**

Run:

```powershell
& 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_exam_service.py -q
```

Expected: failure because lifecycle functions are not implemented.

- [ ] **Step 3: Implement permissions and random practice**

In `services/exam_service.py`, add:

```python
import random
from datetime import datetime, timezone

TAKER_ROLES = {"材料员", "材料审批负责人", "基地负责人"}
MANAGER_ROLES = {"系统管理员", "材料审批负责人"}
OBJECTIVE_TYPES = {"single_choice", "multiple_choice", "true_false"}
SUBJECTIVE_TYPES = {"short_answer", "case_analysis"}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def can_take_exam(user):
    return bool(user and user.get("role_name") in TAKER_ROLES)


def can_manage_exam(user):
    return bool(user and user.get("role_name") in MANAGER_ROLES)


def get_random_practice_questions(limit=10, paper_id=None):
    conn = get_db()
    params = []
    where = ""
    if paper_id:
        where = "WHERE q.paper_id = ?"
        params.append(paper_id)
    rows = conn.execute(
        f"""
        SELECT q.*, p.title AS paper_title
        FROM exam_questions q
        JOIN exam_papers p ON p.id = q.paper_id
        {where}
        """,
        params,
    ).fetchall()
    questions = [dict(row) for row in rows]
    random.shuffle(questions)
    return questions[:limit]
```

- [ ] **Step 4: Implement attempt lifecycle**

Add:

```python
def start_attempt(user_id, paper_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO exam_attempts (user_id, paper_id, status, started_at) VALUES (?, ?, 'in_progress', ?)",
        (user_id, paper_id, now_iso()),
    )
    conn.commit()
    return cursor.lastrowid


def get_attempt(attempt_id):
    conn = get_db()
    return _dict(conn.execute("SELECT * FROM exam_attempts WHERE id = ?", (attempt_id,)).fetchone())


def submit_attempt(attempt_id, answers):
    conn = get_db()
    cursor = conn.cursor()
    attempt = get_attempt(attempt_id)
    questions = get_paper_questions(attempt["paper_id"])
    objective_score = 0
    suggested_subjective_score = 0
    has_subjective = False
    for question in questions:
        answer_text = answers.get(str(question["id"]), "")
        auto_score = 0
        suggested_score = 0
        if question["question_type"] in OBJECTIVE_TYPES:
            auto_score = grade_objective(question, answer_text)
            objective_score += auto_score
        if question["question_type"] in SUBJECTIVE_TYPES:
            has_subjective = True
            suggested_score = suggest_subjective_score(question, answer_text)
            suggested_subjective_score += suggested_score
        cursor.execute(
            """
            INSERT INTO exam_answers (attempt_id, question_id, answer_text, auto_score, suggested_score)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(attempt_id, question_id)
            DO UPDATE SET answer_text = excluded.answer_text,
                          auto_score = excluded.auto_score,
                          suggested_score = excluded.suggested_score
            """,
            (attempt_id, question["id"], answer_text, auto_score, suggested_score),
        )
    status = "pending_review" if has_subjective else "completed"
    final_score = objective_score if not has_subjective else None
    cursor.execute(
        """
        UPDATE exam_attempts
        SET status = ?, objective_score = ?, suggested_subjective_score = ?, final_score = ?, submitted_at = ?
        WHERE id = ?
        """,
        (status, objective_score, suggested_subjective_score, final_score, now_iso(), attempt_id),
    )
    conn.commit()
```

- [ ] **Step 5: Implement reviews and results**

Add result and review functions by porting the stable query shape from `kaoshi/exam_system/services.py`, with table names changed to `exam_*` and user joins changed to zero-material `users`/`roles`. Required return fields:

```python
{
    "attempt_id": 1,
    "user_id": 2,
    "user_name": "张三",
    "username": "zhangsan",
    "role_name": "材料员",
    "paper_title": "第一套（新编实操版）",
    "objective_score": 60,
    "final_score": 92,
    "status": "completed",
}
```

- [ ] **Step 6: Run service tests**

Run:

```powershell
& 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_exam_service.py -q
```

Expected: all service tests pass.

- [ ] **Step 7: Commit**

```powershell
git add services/exam_service.py tests/test_exam_service.py
git commit -m "Add exam center service lifecycle"
```

## Task 4: Exam API Blueprint

**Files:**
- Create: `blueprints/exam.py`
- Modify: `blueprints/__init__.py`
- Modify: `app.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_exam_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_exam_api.py`:

```python
import sqlite3

from services.exam_import_service import import_exam_papers_from_docx


def set_user(client, user_id, role_name):
    with client.session_transaction() as sess:
        sess["user"] = {
            "id": user_id,
            "username": "tester",
            "real_name": "测试用户",
            "role_name": role_name,
            "permissions": "",
        }


def create_role_user(test_db, role_name):
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("INSERT INTO roles (role_name, permissions) VALUES (?, '')", (role_name,))
    role_id = cur.lastrowid
    cur.execute(
        "INSERT INTO users (username, password, real_name, role_id, is_active, create_time) VALUES (?, 'x', '测试用户', ?, 1, '2026-06-26')",
        (role_name, role_id),
    )
    conn.commit()
    return cur.lastrowid


def seed_papers():
    import_exam_papers_from_docx("docs/exam_sources/中天建设项目仓管、收料岗-材料进场验收标准专项考试卷（全新5套完整版）(3).docx")


def test_supplier_cannot_access_exam_center(client, test_db):
    user_id = create_role_user(test_db, "供应商")
    set_user(client, user_id, "供应商")

    response = client.get("/api/exam/summary")

    assert response.status_code == 403
    assert response.get_json()["success"] is False


def test_material_clerk_can_get_summary_and_practice(client, test_db):
    seed_papers()
    user_id = create_role_user(test_db, "材料员")
    set_user(client, user_id, "材料员")

    summary = client.get("/api/exam/summary").get_json()
    practice = client.get("/api/exam/practice/random?limit=5").get_json()

    assert summary["success"] is True
    assert summary["data"]["can_manage"] is False
    assert len(practice["data"]) == 5


def test_material_approval_owner_can_manage_papers(client, test_db):
    seed_papers()
    user_id = create_role_user(test_db, "材料审批负责人")
    set_user(client, user_id, "材料审批负责人")

    response = client.get("/api/exam/admin/papers")

    assert response.status_code == 200
    assert response.get_json()["success"] is True
```

- [ ] **Step 2: Run API tests to verify they fail**

Run:

```powershell
& 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_exam_api.py -q
```

Expected: failure because `/api/exam/*` routes do not exist.

- [ ] **Step 3: Implement blueprint**

Create `blueprints/exam.py`:

```python
"""Exam center API blueprint."""

from flask import Blueprint, jsonify, request, session

from services import exam_service

exam_bp = Blueprint("exam", __name__, url_prefix="/api/exam")


def current_user():
    return session.get("user")


def require_exam_user():
    user = current_user()
    if not exam_service.can_take_exam(user) and not exam_service.can_manage_exam(user):
        return None, (jsonify({"success": False, "message": "无考试中心权限"}), 403)
    return user, None


def require_exam_manager():
    user = current_user()
    if not exam_service.can_manage_exam(user):
        return None, (jsonify({"success": False, "message": "无考试管理权限"}), 403)
    return user, None


@exam_bp.get("/summary")
def summary():
    user, error = require_exam_user()
    if error:
        return error
    return jsonify({
        "success": True,
        "data": {
            "current_paper": exam_service.get_current_exam_paper(),
            "attempts": exam_service.list_user_attempts(user["id"]),
            "can_manage": exam_service.can_manage_exam(user),
        },
    })


@exam_bp.get("/practice/random")
def random_practice():
    _user, error = require_exam_user()
    if error:
        return error
    limit = int(request.args.get("limit", 10))
    return jsonify({"success": True, "data": exam_service.get_random_practice_questions(limit=limit)})


@exam_bp.get("/admin/papers")
def admin_papers():
    _user, error = require_exam_manager()
    if error:
        return error
    return jsonify({"success": True, "data": exam_service.list_papers()})
```

Add the rest of the routes after service tests pass:

```text
GET    /api/exam/papers
POST   /api/exam/admin/current-paper
POST   /api/exam/attempts
GET    /api/exam/attempts/<attempt_id>
POST   /api/exam/attempts/<attempt_id>/submit
GET    /api/exam/results
GET    /api/exam/admin/results
GET    /api/exam/admin/reviews
POST   /api/exam/admin/reviews/<answer_id>
```

- [ ] **Step 4: Register blueprint**

In `blueprints/__init__.py`:

```python
from .exam import exam_bp
```

In `app.py`, add `exam_bp` to the blueprint import list and register it:

```python
app.register_blueprint(exam_bp)
```

In `tests/conftest.py`, include `exam_bp` in the import and `app.register_blueprint(exam_bp)`.

- [ ] **Step 5: Run API tests**

Run:

```powershell
& 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_exam_api.py -q
```

Expected: all API tests pass.

- [ ] **Step 6: Commit**

```powershell
git add blueprints/exam.py blueprints/__init__.py app.py tests/conftest.py tests/test_exam_api.py
git commit -m "Expose exam center API"
```

## Task 5: Front-End Exam Center

**Files:**
- Modify: `index.html`
- Modify: `static/js/app.js`
- Create: `static/js/exam.js`
- Modify: `static/css/style.css`
- Test: `tests/test_frontend_exam.py`

- [ ] **Step 1: Write failing front-end structure tests**

Create `tests/test_frontend_exam.py`:

```python
from pathlib import Path


def test_exam_center_nav_and_module_exist():
    html = Path("index.html").read_text(encoding="utf-8")

    assert 'data-module="exam"' in html
    assert "考试中心" in html
    assert 'id="examModule"' in html


def test_exam_frontend_script_is_loaded():
    html = Path("index.html").read_text(encoding="utf-8")
    js = Path("static/js/app.js").read_text(encoding="utf-8")

    assert "static/js/exam.js" in html
    assert "case 'exam': loadExamCenter(); break;" in js


def test_exam_role_helpers_are_present():
    js = Path("static/js/exam.js").read_text(encoding="utf-8")

    assert "function canUseExamCenter" in js
    assert "材料员" in js
    assert "材料审批负责人" in js
    assert "基地负责人" in js
    assert "系统管理员" in js
```

- [ ] **Step 2: Run front-end tests to verify they fail**

Run:

```powershell
& 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_frontend_exam.py -q
```

Expected: failure because exam UI files are not present.

- [ ] **Step 3: Add nav and module markup**

In `index.html`, add a nav item in the "数据中心" group:

```html
<div class="nav-item" data-module="exam" onclick="showModule('exam')">
    <i data-lucide="graduation-cap"></i> <span class="nav-label">考试中心</span>
</div>
```

Add a module block near other top-level modules:

```html
<div id="examModule" class="module hidden">
    <div class="page-header">
        <h1>考试中心</h1>
        <div class="header-actions" id="examAdminActions"></div>
    </div>
    <div class="exam-tabs">
        <button class="btn btn-secondary" onclick="showExamTab('practice')">随机练习</button>
        <button class="btn btn-secondary" onclick="showExamTab('exam')">正式考试</button>
        <button class="btn btn-secondary" onclick="showExamTab('results')">我的成绩</button>
        <button class="btn btn-secondary exam-manager-only" onclick="showExamTab('papers')">题库管理</button>
        <button class="btn btn-secondary exam-manager-only" onclick="showExamTab('reviews')">阅卷</button>
        <button class="btn btn-secondary exam-manager-only" onclick="showExamTab('adminResults')">成绩查询</button>
    </div>
    <div id="examContent" class="exam-content"></div>
</div>
```

Before the existing app script, load:

```html
<script src="/static/js/exam.js?v=2026062601"></script>
```

- [ ] **Step 4: Add route hook**

In `static/js/app.js`, add to `showModule(module)`:

```javascript
        case 'exam': loadExamCenter(); break;
```

In `applyPermissionControls()`, hide exam nav for users outside allowed roles:

```javascript
    document.querySelectorAll('[data-module="exam"]').forEach(el => {
        el.style.display = canUseExamCenter(currentUser) ? '' : 'none';
    });
```

- [ ] **Step 5: Create exam front-end module**

Create `static/js/exam.js`:

```javascript
let examSummary = null;
let examCurrentTab = 'practice';

function canUseExamCenter(user = currentUser) {
    return ['材料员', '材料审批负责人', '基地负责人', '系统管理员'].includes(user?.role_name);
}

function canManageExam(user = currentUser) {
    return ['系统管理员', '材料审批负责人'].includes(user?.role_name);
}

async function loadExamCenter() {
    if (!canUseExamCenter()) {
        showToast('无考试中心权限', 'error');
        showModule('home');
        return;
    }
    const res = await api('/api/exam/summary');
    const data = await res.json();
    if (!data.success) {
        showToast(data.message || '加载考试中心失败', 'error');
        return;
    }
    examSummary = data.data;
    document.querySelectorAll('.exam-manager-only').forEach(el => {
        el.style.display = canManageExam() ? '' : 'none';
    });
    showExamTab(examCurrentTab);
}

function showExamTab(tab) {
    examCurrentTab = tab;
    const content = document.getElementById('examContent');
    if (tab === 'practice') {
        content.innerHTML = '<div class="panel"><h2>随机练习</h2><button class="btn btn-primary" onclick="loadRandomPractice()">开始随机练习</button><div id="examPracticeList"></div></div>';
    } else if (tab === 'exam') {
        const paper = examSummary?.current_paper;
        content.innerHTML = `<div class="panel"><h2>正式考试</h2><p>${paper ? escapeHtml(paper.title) : '管理员尚未设置考试试卷'}</p><button class="btn btn-primary" onclick="startCurrentExam()" ${paper ? '' : 'disabled'}>开始考试</button></div>`;
    } else if (tab === 'results') {
        content.innerHTML = '<div class="panel"><h2>我的成绩</h2><div id="examResultsTable">加载中...</div></div>';
        loadMyExamResults();
    } else if (canManageExam()) {
        content.innerHTML = '<div class="panel"><h2>考试管理</h2><div id="examAdminPanel">加载中...</div></div>';
    }
}
```

Implement the remaining functions against the API endpoints from Task 4:

```text
loadRandomPractice
startCurrentExam
renderExamQuestions
submitExamAttempt
loadMyExamResults
loadExamPapersAdmin
setCurrentExamPaper
loadPendingReviews
submitReviewScore
loadAllExamResults
```

- [ ] **Step 6: Add responsive styles**

In `static/css/style.css`, add:

```css
.exam-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 16px;
}

.exam-content .panel {
    background: var(--card-bg, #fff);
    border: 1px solid var(--border, #e5e7eb);
    border-radius: 8px;
    padding: 16px;
}

.exam-question {
    border-bottom: 1px solid #e5e7eb;
    padding: 12px 0;
}

.exam-options {
    display: grid;
    gap: 8px;
    margin-top: 8px;
}

@media (max-width: 768px) {
    .exam-tabs .btn {
        flex: 1 1 calc(50% - 8px);
    }
}
```

- [ ] **Step 7: Run front-end tests**

Run:

```powershell
& 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_frontend_exam.py -q
```

Expected: all front-end structure tests pass.

- [ ] **Step 8: Commit**

```powershell
git add index.html static/js/app.js static/js/exam.js static/css/style.css tests/test_frontend_exam.py
git commit -m "Add exam center frontend"
```

## Task 6: Startup Import and Admin Paper Management

**Files:**
- Modify: `services/exam_import_service.py`
- Modify: `blueprints/exam.py`
- Modify: `app.py`
- Test: `tests/test_exam_import_service.py`
- Test: `tests/test_exam_api.py`

- [ ] **Step 1: Add tests for idempotent startup import**

Add to `tests/test_exam_import_service.py`:

```python
from services.exam_import_service import ensure_exam_sources_imported


def test_ensure_exam_sources_imported_is_idempotent(test_db):
    first = ensure_exam_sources_imported()
    second = ensure_exam_sources_imported()

    assert first["paper_count"] == 5
    assert second["paper_count"] == 5
    assert second["created"] is False
```

- [ ] **Step 2: Add tests for current paper management**

Add to `tests/test_exam_api.py`:

```python
def test_manager_can_change_current_paper(client, test_db):
    seed_papers()
    user_id = create_role_user(test_db, "系统管理员")
    set_user(client, user_id, "系统管理员")
    papers = client.get("/api/exam/admin/papers").get_json()["data"]

    response = client.post("/api/exam/admin/current-paper", json={"paper_id": papers[1]["id"]})
    summary = client.get("/api/exam/summary").get_json()

    assert response.get_json()["success"] is True
    assert summary["data"]["current_paper"]["id"] == papers[1]["id"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
& 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_exam_import_service.py tests/test_exam_api.py -q
```

Expected: failures for missing startup import/current-paper endpoint.

- [ ] **Step 4: Implement startup import**

In `services/exam_import_service.py`, add:

```python
from pathlib import Path


def ensure_exam_sources_imported():
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) AS count FROM exam_papers WHERE source_type = 'exam'").fetchone()["count"]
    if existing:
        return {"created": False, "paper_count": existing}
    source_dir = Path("docs/exam_sources")
    source = next(source_dir.glob("*材料进场验收标准专项考试卷*.docx"))
    result = import_exam_papers_from_docx(source)
    return {"created": True, "paper_count": result["inserted"]}
```

In `app.py`, after database initialization imports are available, call this inside app startup if the database is initialized:

```python
from services.exam_import_service import ensure_exam_sources_imported

with app.app_context():
    ensure_exam_sources_imported()
```

If `app.py` startup call is too invasive for tests, call `ensure_exam_sources_imported()` at the end of `init_database()` after `init_exam_schema(conn)` using a direct connection-safe helper.

- [ ] **Step 5: Implement current-paper endpoint**

In `services/exam_service.py`, add:

```python
def set_current_exam_paper(paper_id):
    conn = get_db()
    paper = conn.execute("SELECT id FROM exam_papers WHERE id = ?", (paper_id,)).fetchone()
    if not paper:
        raise ValueError("试卷不存在")
    conn.execute(
        """
        INSERT INTO exam_settings (key, value)
        VALUES ('current_exam_paper_id', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(paper_id),),
    )
    conn.commit()
```

In `blueprints/exam.py`, add:

```python
@exam_bp.post("/admin/current-paper")
def set_current_paper():
    _user, error = require_exam_manager()
    if error:
        return error
    data = request.json or {}
    try:
        exam_service.set_current_exam_paper(int(data.get("paper_id")))
    except (TypeError, ValueError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True})
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
& 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_exam_import_service.py tests/test_exam_api.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```powershell
git add services/exam_import_service.py services/exam_service.py blueprints/exam.py app.py tests/test_exam_import_service.py tests/test_exam_api.py
git commit -m "Seed and manage current exam paper"
```

## Task 7: Full Verification and Browser QA

**Files:**
- Modify if required by verification findings only.

- [ ] **Step 1: Run full automated tests**

Run:

```powershell
& 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run local app**

Start the app in a background PowerShell process:

```powershell
$env:SECRET_KEY='dev-secret'
Start-Process -WindowStyle Hidden -FilePath 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -ArgumentList 'app.py' -WorkingDirectory 'C:\Users\24525\Desktop\CODEX\lingxingcaiguanli-'
```

Expected: local server starts on `http://127.0.0.1:5000`.

- [ ] **Step 3: Verify HTML and static assets**

Run:

```powershell
& 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' - <<'PY'
import urllib.request
html = urllib.request.urlopen('http://127.0.0.1:5000/', timeout=10).read().decode('utf-8')
print('考试中心' in html)
print('/static/js/exam.js' in html)
PY
```

Expected:

```text
True
True
```

- [ ] **Step 4: Verify mobile layout with Playwright**

Use the existing Playwright skill or local browser tooling to load:

```text
http://127.0.0.1:5000/
```

Check desktop width `1440x900` and mobile width `390x844`. Required visual checks:

- The left nav or mobile equivalent does not overlap the exam module.
- Exam tabs wrap cleanly on mobile.
- Question text and option text do not overflow cards.
- Buttons fit inside their containers.

- [ ] **Step 5: Commit any verification-only fixes**

If visual QA requires style changes:

```powershell
git add index.html static/js/exam.js static/css/style.css tests/test_frontend_exam.py
git commit -m "Polish exam center responsive layout"
```

If no fixes are required, do not create an empty commit.

## Task 8: Push and Deploy

**Files:**
- No source edits unless deployment exposes a defect.

- [ ] **Step 1: Confirm clean worktree except known untracked user files**

Run:

```powershell
git status --short
```

Expected: only the pre-existing untracked `2026年5月零星材料采购汇报(2).pdf` and `outputs/` may remain.

- [ ] **Step 2: Push current branch**

Run:

```powershell
git push origin prod
```

Expected: push succeeds.

- [ ] **Step 3: Deploy using existing zero-material workflow**

Use the repo's existing Windows deployment path. If GitHub Actions is the active deployment mechanism, monitor the workflow. If direct server deployment is required, use the existing deploy artifact scripts in `deploy/` and avoid force-pushing.

- [ ] **Step 4: Verify live server**

Using a real internal user account with one of these roles:

```text
材料员
材料审批负责人
基地负责人
系统管理员
```

Verify:

- Login succeeds through the zero-material login page.
- "考试中心" appears for allowed roles.
- "考试中心" is hidden or forbidden for supplier users.
- 系统管理员 and 材料审批负责人 can open paper management.
- Current paper selection controls the employee formal exam paper.
- Random practice returns different question order across repeated loads.
- Results page shows only the current employee's own scores.
- Admin results page shows all scores for exam managers.

- [ ] **Step 5: Final commit marker if deployment scripts changed**

If deployment required code or script changes:

```powershell
git add deploy app.py database services blueprints static index.html tests
git commit -m "Fix exam center deployment integration"
git push origin prod
```

If deployment only used existing scripts, skip this step.

## Self-Review Checklist

- Spec coverage: This plan covers account reuse, internal role permissions, supplier exclusion, `exam_` tables, current-paper enforcement, random practice, reviewing, results, mobile UI, tests, and deployment.
- Placeholder scan: The plan contains concrete files, commands, endpoint names, table names, and expected outputs. No placeholder work remains.
- Type consistency: User identity is always zero-material `users.id`; role checks use `session['user']['role_name']`; exam table names consistently use the `exam_` prefix.
