# Inquiry Import Material Code Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent inquiry quote-sheet imports from failing when one upload creates multiple previously unknown materials.

**Architecture:** Keep the existing import pipeline and delegate new material code allocation to `helpers.material_regions.generate_material_code`. Resolve the draft project's code once before parsing rows, then request a unique region-aware code for every unmatched material.

**Tech Stack:** Python 3, Flask, SQLite, openpyxl, pytest

---

### Task 1: Reproduce the duplicate-code failure

**Files:**
- Modify: `tests/test_inquiry_filters.py`

- [x] **Step 1: Write the failing test**

Add `test_import_draft_quote_sheet_creates_unique_codes_for_multiple_new_materials`. Seed a `KMJJYC` project, a draft inquiry with an existing `KMLX00050` material, export its quote sheet, replace row 4 with `Quartz imported item`, add row 5 as `Zinc imported item`, and post the workbook to the import endpoint. Assert HTTP 200, `success` is true, and the returned codes are `KMLX00051` and `KMLX00052`.

- [x] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_inquiry_filters.py::test_import_draft_quote_sheet_creates_unique_codes_for_multiple_new_materials
```

Expected: FAIL because the old algorithm returns HTTP 500 after attempting to insert the duplicate fallback code.

### Task 2: Use the shared material code generator

**Files:**
- Modify: `blueprints/inquiries.py:3133-3375`
- Test: `tests/test_inquiry_filters.py`

- [x] **Step 1: Resolve the draft project code once**

After validating the draft owner, query `projects.project_code` using `draft["project_id"]`. Use an empty string when the project row is absent.

- [x] **Step 2: Replace the temporary code algorithm**

Replace the `ORDER BY id DESC` and string-splitting block with:

```python
new_code = generate_material_code(cursor, draft_project_code, user)
```

- [x] **Step 3: Commit created materials before returning**

After confirming `parsed_items` is non-empty, call `conn.commit()` before closing the connection. Extend the regression test to query `materials` after the response and assert that both generated codes remain stored.

- [x] **Step 4: Run the focused test**

Run:

```powershell
python -m pytest -q tests/test_inquiry_filters.py::test_import_draft_quote_sheet_creates_unique_codes_for_multiple_new_materials
```

Expected: PASS.

- [x] **Step 5: Run inquiry and full test suites**

Run:

```powershell
python -m pytest -q tests/test_inquiry_filters.py
python -m pytest -q tests
```

Expected: both commands pass with no failures.

### Task 3: Release and verify production

**Files:**
- Modify: `blueprints/inquiries.py`
- Modify: `tests/test_inquiry_filters.py`
- Create: `docs/superpowers/specs/2026-07-30-inquiry-import-material-code-design.md`
- Create: `docs/superpowers/plans/2026-07-30-inquiry-import-material-code.md`

- [ ] **Step 1: Review and commit**

Run `git diff --check`, inspect `git status --short`, stage only the four files above, and commit with:

```powershell
git commit -m "fix: prevent duplicate material codes on inquiry import"
```

- [ ] **Step 2: Push production**

Push the verified commit to `origin/prod`. This triggers the existing production deployment workflow.

- [ ] **Step 3: Verify deployment**

Wait for the `Deploy prod` workflow to finish successfully, verify the production root URL returns HTTP 200, and inspect the deployment log for service startup errors.
