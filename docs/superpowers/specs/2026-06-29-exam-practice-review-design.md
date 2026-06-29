# Exam Practice Review Design

## Goal

Enhance the integrated exam center so daily practice only uses objective questions, true/false questions are answerable, practice submissions show answers immediately, and users can review practice history, wrong questions, and formal exam answer details.

## Scope

This change applies to the zero-material management system exam center. It keeps the existing user account, role, current-paper, formal-exam submission, and admin result permission model.

In scope:
- Random practice draws only `single_choice`, `multiple_choice`, and `true_false` questions.
- True/false questions render answer choices even when the imported DOCX did not provide options.
- Practice submission is persisted per user and returns immediate answer feedback.
- Users can view practice history and wrong-question history repeatedly.
- Formal exam result rows can be opened to review answer details after submission.
- Managers can review formal exam details for results they are allowed to see.

Out of scope:
- Changing formal exam paper selection rules.
- Removing subjective questions from formal exams.
- Changing scoring rules for formal exams.
- Rebuilding the standalone `kaoshi` project.

## Data Model

Keep existing `exam_practice_attempts` and extend it with a `practice_session_id` column. Each submitted practice batch receives a generated session id. One row is stored per answered question with:
- `user_id`
- `question_id`
- `answer_text`
- `is_correct`
- `created_at`
- `practice_session_id`

Existing rows without a session id remain valid. History endpoints will group such older rows under their row id as a fallback.

Formal exam details use the existing `exam_attempts` and `exam_answers` tables. No new formal exam tables are required.

## API Design

Learner endpoints:
- `GET /api/exam/practice/random?limit=10`
  - Returns only objective questions.
  - Keeps answer fields hidden before submission.
- `POST /api/exam/practice/submit`
  - Body: `{ "answers": { "<question_id>": "A" } }`
  - Stores one practice row per submitted question.
  - Returns result items with question, options, user answer, correct answer, `is_correct`, and score.
- `GET /api/exam/practice/history`
  - Returns recent practice rows grouped by session and question.
- `GET /api/exam/practice/wrong`
  - Returns only rows where `is_correct = 0`, grouped for repeat review.
- `GET /api/exam/attempts/<attempt_id>/review`
  - Returns formal exam detail after submission.
  - The owner can view their own attempt.
  - Managers can view any attempt allowed by existing result permissions.

Admin endpoints remain unchanged except they may link to the formal attempt review endpoint.

## Frontend Design

Practice tab:
- Change copy from "does not show answers" to "submit to view answers and save records".
- Render random practice questions with radio/checkbox controls.
- For `true_false`, synthesize two options when missing: `√. 正确` and `×. 错误`.
- On submit, call `/api/exam/practice/submit`, replace the form with a results view, and show each question's answer feedback.
- Add visible sections or buttons for "练习记录" and "错题记录".

Results tab:
- Add a "查看明细" action for each formal exam result row.
- The detail view lists each question with user answer, correct answer/reference answer, score, and correctness when objective.

Manager results:
- Add the same "查看明细" action for managers.

## Error Handling

- Practice submit rejects missing or unknown objective questions with a clear JSON error.
- Practice submit ignores subjective question ids by rejecting them instead of scoring them.
- Formal attempt review returns 404 for missing attempts and 403 for unauthorized users.
- Empty history and empty wrong-question lists render friendly empty states.

## Testing

Add tests before implementation:
- Service test: random practice excludes subjective questions.
- Service/API test: true/false questions have usable options in sanitized payloads.
- API test: practice submit stores rows and returns correct-answer feedback.
- API test: wrong-question endpoint returns only incorrect rows for the current user.
- API test: formal attempt review returns answer details for owner and blocks other learners.
- Frontend static test: practice submit/history/wrong-detail functions and true/false fallback rendering exist.

Run:
- `python -m pytest tests/test_exam_service.py tests/test_exam_api.py tests/test_frontend_exam.py -q`
- `python -m pytest tests -q`

## Deployment

Merge to `prod`, push to GitHub, wait for `Deploy prod` GitHub Actions success, then verify the Windows server:
- Git SHA matches pushed `prod`.
- Service `lxclgl` is running.
- `http://127.0.0.1:5000/` returns 200.
- Exam tables remain populated.
