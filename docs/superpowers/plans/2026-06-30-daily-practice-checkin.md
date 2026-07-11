# Daily Practice Check-in Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daily 30-question practice check-in flow that passes at 80% accuracy and works cleanly on mobile through a dedicated answering page.

**Architecture:** Reuse existing practice answer storage and group answers by `practice_session_id`. Add service helpers for daily statistics, expose them through exam APIs, and adjust the frontend to launch a focused practice page while keeping the original exam center records.

**Tech Stack:** Flask, SQLite, plain JavaScript, pytest, Playwright for browser verification.

---

### Task 1: Back-end practice check-in rules

**Files:**
- Modify: `services/exam_service.py`
- Modify: `blueprints/exam.py`
- Test: `tests/test_exam_service.py`
- Test: `tests/test_exam_api.py`

- [ ] Write failing tests for 30-question default, 80% pass/fail result fields, and daily status.
- [ ] Run focused tests and verify they fail because the new fields/endpoints are missing.
- [ ] Add `DAILY_PRACTICE_QUESTION_COUNT = 30` and `DAILY_PRACTICE_REQUIRED_ACCURACY = 0.8`.
- [ ] Extend `record_practice_answers()` to return totals, accuracy, pass flag, and today's status.
- [ ] Add `get_daily_practice_status(user_id)`.
- [ ] Add `GET /api/exam/practice/daily-status`.
- [ ] Change `/api/exam/practice/random` default limit from 10 to 30.
- [ ] Run focused tests and commit.

### Task 2: Dedicated mobile practice page

**Files:**
- Modify: `app.py`
- Modify: `static/js/exam.js`
- Create: `static/js/exam-practice-page.js`
- Create: `templates/exam_practice.html` if the app uses template routing; otherwise serve a static HTML string through Flask.
- Test: `tests/test_frontend_exam.py`

- [ ] Write failing frontend/static tests for the dedicated route, 30-question request, and pass/fail copy.
- [ ] Run tests and verify they fail.
- [ ] Add `/exam/practice-session` route.
- [ ] Update the exam center practice tab so the start button opens `/exam/practice-session`.
- [ ] Implement focused page script with load, answer collection, submit, result display, continue practice, wrong record, and return actions.
- [ ] Run focused tests and commit.

### Task 3: Verification and deploy

**Files:**
- No production code changes unless verification exposes a bug.

- [ ] Run `node --check static/js/exam.js`.
- [ ] Run `node --check static/js/exam-practice-page.js`.
- [ ] Run focused exam tests.
- [ ] Run full pytest suite.
- [ ] Run browser verification at desktop and mobile viewport.
- [ ] Merge to `prod`, push, monitor deploy, and verify server HEAD/service/API.
