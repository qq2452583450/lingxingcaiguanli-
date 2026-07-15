# Exam Attendance, Retroactive Check-in, and Retake Design

## Goal

Extend the existing exam center with a calendar-based daily attendance view, monthly retroactive check-in limits, month-end attendance comparison reports, and clearly separated make-up exam versus failed-exam retake flows.

## Existing Context

The current exam center already has daily practice sessions, formal exam attempts, manager check-in records, wrong-practice retry, and result administration.

- `exam_practice_attempts` is the source of practice/check-in activity.
- `get_daily_practice_status()` and `list_daily_checkins()` aggregate daily practice sessions.
- `exam_attempts` and `exam_answers` store formal exam submissions and scores.
- The frontend entry point is `static/js/exam.js`; the focused daily practice page is `static/js/exam-practice-page.js`.
- Exam APIs live in `blueprints/exam.py`; service logic lives in `services/exam_service.py`; schema migrations live in `database/exam_schema.py`.

## Attendance Calendar

The daily attendance calendar should reuse practice sessions as the source of truth.

A date is green when the user has at least one qualifying session on that date:

- total answered questions is at least `DAILY_PRACTICE_QUESTION_COUNT` (`30`)
- session accuracy is at least `DAILY_PRACTICE_REQUIRED_ACCURACY` (`0.8`)

A date is red when the date is expected but has no qualifying session.

The calendar API should return one row per date in the requested month:

- `date`
- `status`: `passed`, `missing`, `future`, or `not_required`
- `answered_count`
- `best_accuracy`
- `session_count`
- `can_retro_checkin`
- `retro_checkin_used`
- `retro_checkin_limit`

The first implementation should treat every calendar date up to today as required for eligible exam users. Future dates should not be red and should not support retroactive check-in.

## Retroactive Check-in

Retroactive check-in is a successful practice session written against a past missing date.

Rules:

- The user clicks a red date in the calendar.
- The system opens the normal 30-question practice flow with a `target_date`.
- Submission is only allowed for a past red date.
- The session must meet the same daily pass rule: 30 questions and at least 80% accuracy.
- The monthly allowance is 3 successful retroactive check-ins per natural month.
- A failed retroactive attempt should be recorded as normal practice activity for audit, but it should not consume the monthly allowance or turn the date green.
- A successful retroactive check-in records an audit row and consumes one allowance.

New table: `exam_retroactive_checkins`

- `id`
- `user_id`
- `target_date`
- `month`
- `practice_session_id`
- `answered_count`
- `accuracy`
- `created_at`
- unique `(user_id, target_date)` so a date cannot be retroactively fixed twice

The existing `exam_practice_attempts.created_at` should store the target date for successful retroactive sessions so existing daily aggregations work naturally. The audit table keeps the actual submission timestamp.

## Monthly Attendance Reports

Managers need month-end comparison reports after a full month ends.

New table: `exam_monthly_checkin_reports`

- `id`
- `user_id`
- `month`
- `required_days`
- `passed_days`
- `missing_days`
- `retro_checkin_count`
- `pass_rate`
- `generated_at`
- unique `(user_id, month)`

The first implementation should generate or refresh a report lazily when a manager opens a completed month. That avoids adding Windows scheduled tasks and still gives administrators stable month-end snapshots.

Report rows should compare:

- required dates in the month
- green dates
- red dates
- retroactive check-in usage

Current month reports should stay live and not be persisted as final monthly snapshots.

## Make-up Exam Versus Failed Retake

The system must distinguish two make-up concepts.

Type A: `makeup_absent`

- Meaning: the user did not complete an expected formal exam/task.
- Source: no completed attempt exists for the required paper/task by the due boundary.
- User-facing label key: `makeup_absent`.
- Statistics category: absent/missing exam make-up.

Type B: `retake_failed`

- Meaning: the user completed an exam but did not pass.
- Source: a completed attempt exists with score below the configured passing threshold.
- User-facing label key: `retake_failed`.
- Statistics category: failed exam retake.

New table: `exam_retake_eligibilities`

- `id`
- `user_id`
- `paper_id`
- `eligibility_type`: `makeup_absent` or `retake_failed`
- `source_attempt_id`
- `status`: `open`, `used`, `cancelled`
- `reason`
- `created_at`
- `used_attempt_id`
- `used_at`

Starting an exam from one of these channels should create a normal `exam_attempts` row but also link it back to the eligibility row. The frontend and admin views must show the two channels separately.

## API Shape

User-facing APIs:

- `GET /api/exam/attendance/calendar?month=YYYY-MM`
- `POST /api/exam/attendance/retroactive/start`
- `POST /api/exam/attendance/retroactive/submit`
- `GET /api/exam/retake/eligibilities`
- `POST /api/exam/retake/eligibilities/<id>/start`

Manager APIs:

- `GET /api/exam/admin/attendance/monthly-report?month=YYYY-MM`
- `GET /api/exam/admin/retake/eligibilities`

Existing endpoints should continue to work:

- `/api/exam/practice/daily-status`
- `/api/exam/admin/checkins`
- `/api/exam/attempts`
- `/api/exam/results`

## Frontend Design

User practice tab:

- Add a compact month calendar above the existing daily status card.
- Green dates indicate completed check-in.
- Red past dates indicate missing check-in.
- Clicking a red date starts retroactive practice if quota remains.
- Show a monthly quota label equivalent to "retroactive check-ins X/3" in the calendar header.

Manager check-in tab:

- Keep the current table.
- Add a monthly report view with required days, passed days, missing days, retroactive count, and pass rate.

User results/retake area:

- Add a section for `makeup_absent`.
- Add a separate section for `retake_failed`.
- Do not merge the two lists.

## Data and Migration

Schema migration should be added in `database/exam_schema.py`.

No destructive migration is required. Existing practice and formal exam data remain valid.

Existing historical practice data can populate calendar states through aggregation. Monthly report generation can derive historical rows when requested.

## Testing Strategy

Service tests:

- calendar marks passed, missing, future correctly
- retroactive check-in succeeds only on red past date
- monthly quota allows 3 successful retroactive check-ins and rejects the 4th
- failed retroactive practice does not consume quota
- monthly report counts required, passed, missing, and retroactive days
- `makeup_absent` and `retake_failed` eligibility records are separate and queryable

API tests:

- takers can view their calendar
- managers can view monthly reports
- unauthorized roles are denied
- retake start consumes only the selected eligibility type

Frontend static tests:

- calendar endpoints and render functions exist
- retroactive check-in controls are wired
- retake labels for `makeup_absent` and `retake_failed` both appear

## Deployment

This is a normal `prod` deployment through the existing GitHub Actions workflow. No manual server task is required.

After deployment, verify:

- `/api/exam/summary` still responds
- calendar API for the current user returns month data
- manager monthly report returns rows for a completed month
- existing daily check-in table still loads
