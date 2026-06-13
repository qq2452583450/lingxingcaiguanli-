# Inquiry Approval Print Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the purchase inquiry approval print page to match the confirmed Excel-like horizontal comparison layout.

**Architecture:** Keep the existing `/api/purchase-inquiries/<id>/approval-print` route and replace only its HTML generation. Continue querying the same inquiry, item, quote, and approval record data, then render suppliers as horizontal columns and selected totals as a compact summary.

**Tech Stack:** Flask blueprint HTML response, SQLite rows via existing helpers, pytest route tests.

---

### Task 1: Add Coverage For New Print Layout

**Files:**
- Modify: `tests/test_inquiry_filters.py`

- [ ] **Step 1: Write failing tests**

Add a test that creates one approved inquiry with two materials and two suppliers, then requests `/api/purchase-inquiries/<id>/approval-print`.

Assert:
- `零星材采购比价审批签字单` appears.
- Supplier names appear as horizontal quote headers.
- Selected supplier totals appear.
- `申请人签字`, `材料员签字`, `项目负责人签字` appear.
- `总经理签字` does not appear.
- `项目管理处` still appears.

- [ ] **Step 2: Run the focused test**

Run: `pytest tests/test_inquiry_filters.py::test_approval_print_uses_excel_like_supplier_columns_and_selected_totals -q`

Expected before implementation: FAIL because the current print layout does not contain the new title, supplier-total class/labels, and simplified signature section.

### Task 2: Implement Excel-Like Print HTML

**Files:**
- Modify: `blueprints/inquiries.py`

- [ ] **Step 1: Add render helpers inside `print_inquiry_approval`**

Use small local helpers for money formatting, safe text fallback, project display, supplier discovery, and selected totals.

- [ ] **Step 2: Replace the new-structure table**

Render fixed material columns followed by one supplier quote column per supplier and a final selected supplier column.

- [ ] **Step 3: Replace totals and signature section**

Render supplier selected totals, total amount with Chinese uppercase amount, three signature cells, and the existing project management approval table below.

- [ ] **Step 4: Preserve legacy output**

Keep old-structure data printable with a simplified table and the same totals/signature/approval footer.

### Task 3: Verify

**Files:**
- Test: `tests/test_inquiry_filters.py`

- [ ] **Step 1: Run focused print test**

Run: `pytest tests/test_inquiry_filters.py::test_approval_print_uses_excel_like_supplier_columns_and_selected_totals -q`

Expected: PASS.

- [ ] **Step 2: Run inquiry test group**

Run: `pytest tests/test_inquiry_filters.py -q`

Expected: PASS.
