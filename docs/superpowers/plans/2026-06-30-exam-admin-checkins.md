# Exam Admin Check-ins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add manager-visible daily check-in records and formal exam result deletion.

**Architecture:** Reuse existing exam roles and practice attempt storage. Add service helpers for check-in aggregation and attempt deletion, expose manager-only API routes, then wire them into the existing exam center admin UI.

**Tech Stack:** Flask, SQLite, plain JavaScript, pytest, Node syntax checks, Playwright verification.

---

### Task 1: Manager Check-in Report API

**Files:**
- Modify: `services/exam_service.py`
- Modify: `blueprints/exam.py`
- Test: `tests/test_exam_service.py`
- Test: `tests/test_exam_api.py`

- [ ] Write failing tests for a report containing passed, practiced-not-passed, and not-practiced internal takers.
- [ ] Write failing API tests for `GET /api/exam/admin/checkins?date=YYYY-MM-DD`, manager access, and material clerk denial.
- [ ] Implement `list_daily_checkins(target_date)`.
- [ ] Add manager-only route `/api/exam/admin/checkins`.
- [ ] Run focused tests and commit.

### Task 2: Formal Result Deletion API

**Files:**
- Modify: `services/exam_service.py`
- Modify: `blueprints/exam.py`
- Test: `tests/test_exam_service.py`
- Test: `tests/test_exam_api.py`

- [ ] Write failing tests proving deleting an exam attempt removes exam answers and reviews but leaves practice attempts.
- [ ] Write failing API tests for manager delete success and material clerk delete denial.
- [ ] Implement `delete_exam_attempt(attempt_id)`.
- [ ] Add manager-only `DELETE /api/exam/admin/attempts/<attempt_id>`.
- [ ] Run focused tests and commit.

### Task 3: Admin UI

**Files:**
- Modify: `index.html`
- Modify: `static/js/exam.js`
- Test: `tests/test_frontend_exam.py`

- [ ] Write failing frontend tests for check-in tab markup, check-in API usage, filter buttons, and result delete action.
- [ ] Add manager-only check-in tab.
- [ ] Implement `loadCheckinRecords`, `renderCheckinRecords`, `setCheckinFilter`, and `deleteExamAttempt`.
- [ ] Add delete buttons to admin results only.
- [ ] Run frontend tests, JS syntax checks, and commit.

### Task 4: Verification and Deployment

**Files:**
- No production code changes unless verification exposes a bug.

- [ ] Run `node --check static/js/exam.js`.
- [ ] Run focused exam tests.
- [ ] Run full pytest suite.
- [ ] Run browser verification for manager check-ins and result deletion UI visibility.
- [ ] Merge to `prod`, push, deploy to server, and verify HEAD/service/API.
