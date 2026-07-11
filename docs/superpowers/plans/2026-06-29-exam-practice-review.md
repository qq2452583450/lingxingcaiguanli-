# Exam Practice Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add objective-only practice, true/false answer controls, immediate practice answer feedback, wrong-question history, practice history, and formal exam answer review.

**Architecture:** Extend the existing Flask exam service and blueprint with practice submission/history helpers and formal attempt detail helpers. Keep the frontend inside the existing `static/js/exam.js` module, using the current tab and table patterns. Reuse existing `exam_practice_attempts`, `exam_attempts`, and `exam_answers`; add one nullable session column for grouping practice rows.

**Tech Stack:** Flask, SQLite, vanilla JavaScript, pytest, existing GitHub Actions Windows deployment.

---

## File Structure

- Modify `database/exam_schema.py`: add `practice_session_id` to `exam_practice_attempts` and an index for user/session history.
- Modify `database/auto_fix.py`: auto-add the nullable column for existing server databases.
- Modify `services/exam_service.py`: add objective-only practice query, practice submission/history/wrong helpers, true/false option fallback, formal attempt review helper.
- Modify `blueprints/exam.py`: add practice submit/history/wrong endpoints and formal attempt review endpoint; include true/false fallback in sanitized question payloads.
- Modify `static/js/exam.js`: render true/false fallback choices, submit practice to backend, show answer feedback, show practice/wrong history, link formal results to detail.
- Modify tests:
  - `tests/test_exam_schema.py`
  - `tests/test_exam_service.py`
  - `tests/test_exam_api.py`
  - `tests/test_frontend_exam.py`

---

### Task 1: Practice Schema Migration

**Files:**
- Modify: `database/exam_schema.py`
- Modify: `database/auto_fix.py`
- Test: `tests/test_exam_schema.py`

- [ ] **Step 1: Write failing schema test**

Add this test to `tests/test_exam_schema.py`:

```python
def test_exam_practice_attempts_have_session_id(test_db):
    columns = {row[1]: row for row in test_db.execute("PRAGMA table_info(exam_practice_attempts)")}
    assert "practice_session_id" in columns
    indexes = [row[1] for row in test_db.execute("PRAGMA index_list(exam_practice_attempts)")]
    assert "idx_exam_practice_session" in indexes
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_exam_schema.py::test_exam_practice_attempts_have_session_id -q
```

Expected: fail because `practice_session_id` does not exist.

- [ ] **Step 3: Add schema column and index**

In `database/exam_schema.py`, change the practice table statement to include:

```sql
practice_session_id TEXT,
```

Add this index to the `statements` list:

```python
"CREATE INDEX IF NOT EXISTS idx_exam_practice_session ON exam_practice_attempts(user_id, practice_session_id)",
```

- [ ] **Step 4: Add auto-fix migration**

In `database/auto_fix.py`, add `practice_session_id` to the existing column repair flow for `exam_practice_attempts`:

```python
_ensure_column(conn, "exam_practice_attempts", "practice_session_id", "TEXT")
```

Use the repo's existing helper or local pattern; do not create a second migration framework.

- [ ] **Step 5: Verify and commit**

Run:

```powershell
C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_exam_schema.py -q
```

Expected: pass.

Commit:

```powershell
git add database/exam_schema.py database/auto_fix.py tests/test_exam_schema.py
git commit -m "Add practice session tracking schema"
```

---

### Task 2: Practice Service Behavior

**Files:**
- Modify: `services/exam_service.py`
- Test: `tests/test_exam_service.py`

- [ ] **Step 1: Write failing service tests**

Add imports in `tests/test_exam_service.py`:

```python
from services.exam_service import (
    get_attempt,
    get_attempt_review,
    get_random_practice_questions,
    list_practice_history,
    list_wrong_practice_questions,
    record_practice_answers,
)
```

Add tests:

```python
def test_random_practice_excludes_subjective_questions(test_db):
    seed_exam()
    paper = _first_paper(test_db)

    questions = get_random_practice_questions(limit=50, paper_id=paper["id"])

    assert questions
    assert {q["question_type"] for q in questions} <= {"single_choice", "multiple_choice", "true_false"}


def test_record_practice_answers_scores_and_lists_history(test_db):
    seed_exam()
    user_id = _seed_user(test_db, "practice_clerk", "练习材料员", "材料员")
    paper = _first_paper(test_db)
    questions = get_random_practice_questions(limit=10, paper_id=paper["id"])
    objective = next(q for q in questions if q["question_type"] in {"single_choice", "true_false"})
    wrong_answer = "B" if objective["correct_answer"] != "B" else "A"

    result = record_practice_answers(user_id, {str(objective["id"]): wrong_answer})
    history = list_practice_history(user_id)
    wrong = list_wrong_practice_questions(user_id)

    assert result["session_id"]
    assert result["items"][0]["question_id"] == objective["id"]
    assert result["items"][0]["answer_text"] == wrong_answer
    assert result["items"][0]["correct_answer"] == objective["correct_answer"]
    assert result["items"][0]["is_correct"] is False
    assert history[0]["session_id"] == result["session_id"]
    assert wrong[0]["question_id"] == objective["id"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_exam_service.py::test_random_practice_excludes_subjective_questions tests\test_exam_service.py::test_record_practice_answers_scores_and_lists_history -q
```

Expected: fail because service helpers do not exist or behavior includes subjective questions.

- [ ] **Step 3: Implement objective-only random practice**

In `services/exam_service.py`, update `get_random_practice_questions` so it always adds:

```sql
q.question_type IN ('single_choice', 'multiple_choice', 'true_false')
```

Build the `WHERE` clause with both optional `paper_id` and the objective condition.

- [ ] **Step 4: Implement true/false option fallback helper**

Add:

```python
def ensure_question_options(question: dict) -> dict:
    if question.get("question_type") == "true_false" and not question.get("options"):
        question = dict(question)
        question["options"] = [
            {"key": "√", "text": "正确"},
            {"key": "×", "text": "错误"},
        ]
    return question
```

Call it in `get_paper_questions` and `get_random_practice_questions` before returning.

- [ ] **Step 5: Implement practice recording helpers**

Add:

```python
from uuid import uuid4

def record_practice_answers(user_id: int, answers: dict) -> dict:
    session_id = uuid4().hex
    now = _now()
    # Load submitted objective questions by id, reject missing/non-objective ids.
    # Score with grade_objective and insert rows into exam_practice_attempts.
    # Return {"session_id": session_id, "items": [...]}.
```

Each item must include `question_id`, `question_type`, `stem`, `paper_title`, `options`, `answer_text`, `correct_answer`, `reference_answer`, `is_correct`, `score`, and `created_at`.

Add:

```python
def list_practice_history(user_id: int, limit: int = 100) -> list[dict]:
    # Return latest rows for this user, including question and paper fields.

def list_wrong_practice_questions(user_id: int, limit: int = 100) -> list[dict]:
    # Same shape, filtered to is_correct = 0.
```

- [ ] **Step 6: Verify and commit**

Run:

```powershell
C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_exam_service.py -q
```

Expected: pass.

Commit:

```powershell
git add services/exam_service.py tests/test_exam_service.py
git commit -m "Record practice answers and wrong questions"
```

---

### Task 3: Practice and Review API

**Files:**
- Modify: `blueprints/exam.py`
- Modify: `services/exam_service.py`
- Test: `tests/test_exam_api.py`

- [ ] **Step 1: Write failing API tests**

Add tests to `tests/test_exam_api.py`:

```python
def test_practice_submit_returns_answers_and_persists_history(client, test_db):
    seed_exam()
    clerk_id = seed_user(test_db, "practice_api", "练习接口", ROLE_CLERK)
    login(client, clerk_id, "practice_api", "练习接口", ROLE_CLERK)
    practice = client.get("/api/exam/practice/random?limit=10").get_json()
    question = next(q for q in practice["data"] if q["question_type"] in {"single_choice", "true_false"})
    correct = test_db.execute(
        "SELECT correct_answer FROM exam_questions WHERE id = ?",
        (question["id"],),
    ).fetchone()["correct_answer"]

    submit = client.post(
        "/api/exam/practice/submit",
        json={"answers": {str(question["id"]): correct}},
        headers=csrf_headers(),
    ).get_json()
    history = client.get("/api/exam/practice/history").get_json()

    assert submit["success"] is True
    assert submit["data"]["items"][0]["correct_answer"] == correct
    assert submit["data"]["items"][0]["is_correct"] is True
    assert history["success"] is True
    assert history["data"][0]["question_id"] == question["id"]


def test_wrong_practice_endpoint_scopes_to_current_user(client, test_db):
    seed_exam()
    clerk_id = seed_user(test_db, "wrong_api", "错题接口", ROLE_CLERK)
    other_id = seed_user(test_db, "other_wrong_api", "其他材料员", ROLE_CLERK)
    question = get_paper_questions(papers(test_db)[0]["id"])[0]
    wrong_answer = "B" if question["correct_answer"] != "B" else "A"
    from services.exam_service import record_practice_answers
    record_practice_answers(clerk_id, {str(question["id"]): wrong_answer})
    record_practice_answers(other_id, {str(question["id"]): wrong_answer})
    login(client, clerk_id, "wrong_api", "错题接口", ROLE_CLERK)

    data = client.get("/api/exam/practice/wrong").get_json()

    assert data["success"] is True
    assert len(data["data"]) == 1
    assert data["data"][0]["question_id"] == question["id"]
```

- [ ] **Step 2: Write failing formal review API test**

Add:

```python
def test_attempt_review_returns_answer_details_for_owner_only(client, test_db):
    seed_exam()
    clerk_id = seed_user(test_db, "review_owner", "回看本人", ROLE_CLERK)
    other_id = seed_user(test_db, "review_other", "其他人员", ROLE_CLERK)
    login(client, clerk_id, "review_owner", "回看本人", ROLE_CLERK)
    current_paper = papers(test_db)[0]
    objective = next(q for q in get_paper_questions(current_paper["id"]) if q["question_type"] in {"single_choice", "true_false"})
    start = client.post("/api/exam/attempts", json={}, headers=csrf_headers()).get_json()
    attempt_id = start["attempt_id"]
    client.post(
        f"/api/exam/attempts/{attempt_id}/submit",
        json={"answers": {str(objective["id"]): objective["correct_answer"]}},
        headers=csrf_headers(),
    )

    owner_review = client.get(f"/api/exam/attempts/{attempt_id}/review").get_json()
    login(client, other_id, "review_other", "其他人员", ROLE_CLERK)
    other_response = client.get(f"/api/exam/attempts/{attempt_id}/review")

    assert owner_review["success"] is True
    assert owner_review["data"]["attempt"]["id"] == attempt_id
    assert owner_review["data"]["items"][0]["answer_text"] == objective["correct_answer"]
    assert owner_review["data"]["items"][0]["correct_answer"] == objective["correct_answer"]
    assert other_response.status_code == 403
```

- [ ] **Step 3: Run API tests to verify failure**

Run:

```powershell
C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_exam_api.py::test_practice_submit_returns_answers_and_persists_history tests\test_exam_api.py::test_wrong_practice_endpoint_scopes_to_current_user tests\test_exam_api.py::test_attempt_review_returns_answer_details_for_owner_only -q
```

Expected: fail because endpoints/helpers are missing.

- [ ] **Step 4: Add service formal attempt review helper**

In `services/exam_service.py`, add:

```python
def get_attempt_review(attempt_id: int) -> dict | None:
    # Return {"attempt": attempt, "items": [...]}.
    # Join exam_answers, exam_questions, exam_question_options, exam_papers.
    # Include correct_answer/reference_answer only after the attempt is not in_progress.
```

- [ ] **Step 5: Add blueprint imports and endpoints**

In `blueprints/exam.py`, import:

```python
get_attempt_review,
list_practice_history,
list_wrong_practice_questions,
record_practice_answers,
```

Add:

```python
@exam_bp.route("/practice/submit", methods=["POST"])
def submit_practice():
    user, denied = _require_exam_user()
    if denied:
        return denied
    if not can_take_exam(user):
        return _json_error("Permission denied", 403)
    data = request.get_json(silent=True) or {}
    try:
        result = record_practice_answers(user["id"], data.get("answers") or {})
    except ValueError as exc:
        return _json_error(str(exc), 400)
    return jsonify({"success": True, "data": result})
```

Add `practice/history`, `practice/wrong`, and `attempts/<int:attempt_id>/review` with the permission rules from the spec.

- [ ] **Step 6: Verify and commit**

Run:

```powershell
C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_exam_api.py -q
```

Expected: pass.

Commit:

```powershell
git add blueprints/exam.py services/exam_service.py tests/test_exam_api.py
git commit -m "Expose practice history and attempt review APIs"
```

---

### Task 4: Frontend Practice Feedback and History

**Files:**
- Modify: `static/js/exam.js`
- Test: `tests/test_frontend_exam.py`

- [ ] **Step 1: Write failing static frontend test**

Add to `tests/test_frontend_exam.py`:

```python
def test_exam_frontend_supports_practice_feedback_and_history():
    script = Path("static/js/exam.js").read_text(encoding="utf-8")

    assert "/api/exam/practice/submit" in script
    assert "/api/exam/practice/history" in script
    assert "/api/exam/practice/wrong" in script
    assert "renderPracticeResult" in script
    assert "loadPracticeHistory" in script
    assert "loadWrongPracticeQuestions" in script
    assert "ensureTrueFalseOptions" in script
    assert "/review" in script
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_frontend_exam.py::test_exam_frontend_supports_practice_feedback_and_history -q
```

Expected: fail because frontend functions/endpoints are missing.

- [ ] **Step 3: Add true/false fallback renderer**

In `static/js/exam.js`, add:

```javascript
function ensureTrueFalseOptions(question) {
    if (question.question_type !== 'true_false') return Array.isArray(question.options) ? question.options : [];
    const options = Array.isArray(question.options) ? question.options.filter(option => option.key) : [];
    return options.length ? options : [
        { key: '√', text: '正确' },
        { key: '×', text: '错误' }
    ];
}
```

Use it in `renderQuestionOptions`.

- [ ] **Step 4: Submit practice to backend**

Change `submitPracticeAnswers` to:

```javascript
async function submitPracticeAnswers(event) {
    event.preventDefault();
    const form = event.target;
    const submitButton = form.querySelector('button[type="submit"]');
    if (submitButton) submitButton.disabled = true;
    try {
        const result = await examJson('/api/exam/practice/submit', {
            method: 'POST',
            body: JSON.stringify({ answers: collectExamAnswers(form) })
        });
        renderPracticeResult(result.data || {});
    } catch (e) {
        if (submitButton) submitButton.disabled = false;
        examNotify(e.message || '练习提交失败', 'error');
    }
}
```

- [ ] **Step 5: Add result/history/wrong renderers**

Add functions:

```javascript
function renderPracticeResult(result) { /* show per-question answer, correct answer, is_correct */ }
async function loadPracticeHistory() { /* GET /api/exam/practice/history */ }
async function loadWrongPracticeQuestions() { /* GET /api/exam/practice/wrong */ }
function renderPracticeRecordList(records, emptyText) { /* shared table/card list */ }
```

Add buttons in the practice tab toolbar:

```html
<button ... onclick="loadPracticeHistory()">练习记录</button>
<button ... onclick="loadWrongPracticeQuestions()">错题记录</button>
```

- [ ] **Step 6: Add formal result detail action**

In `renderResultsTable`, add a `查看明细` button that calls:

```javascript
async function viewExamAttemptReview(attemptId) {
    examLoading('正在加载答题明细...');
    const data = await examJson(`/api/exam/attempts/${attemptId}/review`);
    renderAttemptReview(data.data || {});
}
```

Render attempt review with each question, answer, correct/reference answer, and score.

- [ ] **Step 7: Verify and commit**

Run:

```powershell
C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests/test_frontend_exam.py -q
```

Expected: pass.

Commit:

```powershell
git add static/js/exam.js tests/test_frontend_exam.py
git commit -m "Add exam practice feedback UI"
```

---

### Task 5: Full Verification and Browser QA

**Files:**
- No planned source edits unless QA finds a bug.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests/test_exam_schema.py tests/test_exam_service.py tests/test_exam_api.py tests/test_frontend_exam.py -q
```

Expected: all pass.

- [ ] **Step 2: Run full tests**

Run:

```powershell
C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests -q
```

Expected: all pass.

- [ ] **Step 3: Start local Flask server**

Run:

```powershell
$env:SECRET_KEY='dev-secret'; $env:FLASK_DEBUG='False'
Start-Process -WindowStyle Hidden -FilePath 'C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -ArgumentList 'app.py' -WorkingDirectory '<worktree-path>'
```

- [ ] **Step 4: Browser QA**

Use Playwright to verify:
- Login as material clerk.
- Open exam center.
- Random practice shows only choice/true-false controls, no textarea.
- True/false questions have clickable radio options when present.
- Submit practice shows correct answer feedback.
- Practice history and wrong-question history load.
- Formal result row has detail view.
- Mobile width 390 has no horizontal overflow.

- [ ] **Step 5: Commit any QA fixes**

If QA finds a bug, write a failing test first, fix it, rerun focused and full tests, then commit.

---

### Task 6: Merge, Push, Deploy

**Files:**
- No source edits expected.

- [ ] **Step 1: Merge feature branch into `prod`**

Run from main repo:

```powershell
git fetch origin
git checkout prod
git merge origin/prod
git merge <feature-branch>
```

- [ ] **Step 2: Verify after merge**

Run:

```powershell
C:\Users\24525\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests -q
```

Expected: all pass.

- [ ] **Step 3: Push prod**

Run:

```powershell
git push origin prod
```

- [ ] **Step 4: Wait for GitHub Actions**

Poll the newest `Deploy prod` run for the pushed SHA. Expected: `completed success`.

- [ ] **Step 5: Verify server**

Over SSH, verify:
- `git rev-parse HEAD` equals pushed SHA.
- `Get-Service lxclgl` is `Running`.
- `Invoke-WebRequest http://127.0.0.1:5000/` returns 200.
- `exam_papers`, `exam_questions`, and `exam_practice_attempts` exist.

---

## Self-Review

Spec coverage:
- Objective-only practice: Task 2 and Task 3.
- True/false answer fallback: Task 2 and Task 4.
- Practice answer feedback: Task 2, Task 3, Task 4.
- Practice history and wrong records: Task 2, Task 3, Task 4.
- Formal attempt review: Task 3 and Task 4.
- Tests and deployment: Task 5 and Task 6.

Placeholder scan:
- No `TBD`, `TODO`, or unspecified implementation placeholders remain.

Type consistency:
- Function names are consistent across service, API, and frontend steps.
