# Daily Practice Check-in Design

## Goal

The exam center practice flow becomes a daily mobile-friendly check-in: each practice session uses at least 30 objective questions, a session passes only when accuracy is at least 80%, and users keep practicing until one session for the current day passes.

## Behavior

- Practice sessions request 30 questions by default.
- Practice questions remain objective-only: single choice, multiple choice, and true/false.
- Submitting a practice session records every answer under one session id.
- The response includes `total_count`, `correct_count`, `accuracy`, `passed`, and `required_accuracy`.
- A user is considered checked in for the day when any session submitted today has accuracy >= 80%.
- The daily status endpoint reports whether today is passed, the best accuracy, today's session count, today's answered question count, and the required accuracy.
- If a session is below 80%, the UI shows a clear continue-practice action.

## Mobile Flow

The main exam center practice tab keeps summary, status, and record buttons. Starting practice opens a dedicated practice page so mobile users answer in a focused layout without the surrounding management interface. The dedicated page loads the same authenticated session and renders only the practice form, progress text, submit button, result, and return actions.

## Data Model

No new table is needed. Existing `exam_practice_attempts.practice_session_id` and `created_at` are enough to group sessions and compute daily status. Statistics are derived from recorded answers.

## Testing

- Service tests cover daily status and 80% pass/fail calculations.
- API tests cover default 30 question limit, submit response statistics, and daily status endpoint.
- Frontend static tests cover the dedicated practice page entry, default 30-question request, and pass/fail display strings.
