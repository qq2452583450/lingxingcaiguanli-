# Exam Admin Check-ins Design

## Goal

System administrators and material approval owners can see daily practice check-ins for all internal exam takers, identify who has not practiced, and delete formal exam result records from the admin results view.

## Check-in Records

- Add a manager-only check-in records view in the exam center.
- The default date is today. Managers can query another date with a date input.
- The report includes every active internal exam taker whose role is one of: material clerk, material approval owner, or base owner.
- Each row shows username, real name, role, whether they practiced, whether they passed the daily check-in, answered question count, session count, best accuracy, and latest practice time.
- Filters are client-side: all, passed, practiced but not passed, and not practiced.
- Daily practice remains auto-graded only and never appears in the review queue.

## Formal Result Deletion

- Add a manager-only DELETE endpoint for formal exam attempts.
- Deleting an attempt removes its exam answers and subjective review records. Practice attempts, wrong-question records, and check-in records are not touched.
- The admin results table shows a delete action for system administrators and material approval owners.
- Ordinary exam takers cannot delete results.

## Data Model

No schema change is required. Check-ins are derived from `users`, `roles`, and `exam_practice_attempts`. Result deletion uses existing foreign-key relationships plus explicit deletion of subjective review rows for compatibility with SQLite configurations where foreign keys might not be enforced.

## Verification

- Service tests cover report classification and formal attempt deletion.
- API tests cover manager access, taker denial, check-in report endpoint, and delete endpoint.
- Frontend tests cover the new check-in tab, filters, endpoint usage, and delete button wiring.
