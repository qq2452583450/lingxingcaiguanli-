# Draft Quote Export Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the draft inquiry quote export action into the inquiry detail toolbar and add quote-sheet import that fills inquiry detail rows from the exported Excel template.

**Architecture:** Reuse the existing `/api/purchase-inquiries/draft/<id>/export-quote-sheet` workbook as the single template. Add a matching import endpoint that parses the workbook with `openpyxl`, validates ownership/status, maps rows to existing materials and suppliers, and returns structured rows for the frontend to merge into `inquiryItems`. Keep persistence unchanged: imported rows are applied to the current edit form and saved through existing draft/submit flows.

**Tech Stack:** Flask blueprints, SQLite via `get_db()`, `openpyxl`, vanilla JavaScript in `static/js/app.js`, pytest.

---

### Task 1: Frontend Button Placement Tests

**Files:**
- Modify: `tests/test_frontend_special_approval.py`
- Modify: `static/js/app.js`

- [ ] **Step 1: Write failing frontend structure tests**

Add assertions that draft rows no longer render `exportDraftQuoteSheet(${d.id})`, while inquiry detail toolbar renders `exportDraftQuoteSheet(${i.id})` and `importDraftQuoteSheet(${i.id})`.

```python
def test_frontend_draft_rows_do_not_include_export_quote_sheet_action():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    render_drafts_start = source.index("function renderDraftsTable")
    render_drafts_end = source.index("async function deleteInquiryDraft")
    render_drafts = source[render_drafts_start:render_drafts_end]
    assert "exportDraftQuoteSheet(${d.id})" not in render_drafts


def test_frontend_inquiry_detail_toolbar_includes_export_and_import_quote_sheet_actions():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    view_start = source.index("async function viewInquiry")
    view_end = source.index("async function editInquiry")
    view_body = source[view_start:view_end]
    assert "exportDraftQuoteSheet(${i.id})" in view_body
    assert "importDraftQuoteSheet(${i.id})" in view_body
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_frontend_special_approval.py -q`

Expected: Fail because export still appears in `renderDraftsTable` and import is missing from `viewInquiry`.

- [ ] **Step 3: Move export button and add import button**

In `static/js/app.js`, update the toolbar inside `viewInquiry()`:

```javascript
${qs === 'draft' ? `<button class="btn btn-primary" onclick="publishQuotes(${i.id})">发布给供应商报价</button>` : ''}
<a href="/supplier-portal" target="_blank" class="btn btn-secondary" style="text-decoration:none;">供应商报价入口</a>
${i.approval_status === '草稿' && currentUser && i.applicant_id === currentUser.id ? `<button class="btn btn-secondary" onclick="exportDraftQuoteSheet(${i.id})">询比价导出</button>` : ''}
${i.approval_status === '草稿' && currentUser && i.applicant_id === currentUser.id ? `<button class="btn btn-secondary" onclick="importDraftQuoteSheet(${i.id})">询比价导入</button>` : ''}
```

Remove the `exportDraftQuoteSheet(${d.id})` button from `renderDraftsTable()`.

- [ ] **Step 4: Run tests and verify pass**

Run: `pytest tests/test_frontend_special_approval.py -q`

Expected: Pass.

### Task 2: Backend Import Endpoint

**Files:**
- Modify: `blueprints/inquiries.py`
- Modify: `tests/test_inquiry_filters.py`

- [ ] **Step 1: Write failing import endpoint test**

Create a draft inquiry, export the workbook, edit row 4 values in memory, upload it back, and assert the response contains one parsed item with matched material and supplier quote.

```python
def test_import_draft_quote_sheet_parses_exported_template(client, test_db):
    # Seed applicant, project, material, supplier, draft item and quote.
    # Export workbook from /export-quote-sheet.
    # Update row 4 quantity and supplier price.
    # POST workbook to /import-quote-sheet.
    # Assert parsed item includes material_id, detail_spec, brand, quantity, and quote tax_price.
```

Use `BytesIO`, `load_workbook`, and `client.post(..., data={"file": (output, "quote.xlsx")}, content_type="multipart/form-data")`.

- [ ] **Step 2: Run test and verify failure**

Run: `pytest tests/test_inquiry_filters.py::test_import_draft_quote_sheet_parses_exported_template -q`

Expected: Fail with 404 because endpoint does not exist.

- [ ] **Step 3: Implement endpoint**

Add route:

```python
@inquiry_bp.route('/purchase-inquiries/draft/<int:draft_id>/import-quote-sheet', methods=['POST'])
def import_draft_quote_sheet(draft_id):
    from openpyxl import load_workbook
    from io import BytesIO
```

Validate:
- session user exists
- draft exists
- `approval_status == '草稿'`
- `applicant_id == user['id']`
- request has `file`
- workbook headers include `材料名称`, `规格型号`, `详细规格`, `品牌`, `单位`, `数量`

Parse:
- header row is row 3
- data starts at row 4
- base columns are A-H
- supplier price columns start at I and alternate unit price / total amount
- supplier name is extracted from headers ending in `单价...`

Material match SQL:

```sql
SELECT m.id, m.material_code, m.material_name, m.specification, m.detail_spec, m.brand,
       u.unit_name, m.tax_price, m.cash_price
FROM materials m
LEFT JOIN units u ON u.id = m.unit_id
WHERE m.material_name = ?
  AND COALESCE(m.specification, '') = ?
  AND COALESCE(m.detail_spec, '') = ?
  AND COALESCE(m.brand, '') = ?
  AND COALESCE(u.unit_name, '') = ?
LIMIT 1
```

Supplier match SQL:

```sql
SELECT id, supplier_name FROM suppliers WHERE supplier_name = ? LIMIT 1
```

Return:

```json
{
  "success": true,
  "items": [
    {
      "material_id": 1,
      "material_name": "测试材料",
      "specification": "DN25",
      "detail_spec": "加厚",
      "brand": "测试品牌",
      "unit_name": "个",
      "quantity": 5,
      "is_national_standard": 1,
      "unmatched_material": false,
      "quotes": [
        {"supplier_id": 1, "supplier_name": "测试供应商", "tax_price": 12.5, "tax_rate": 0.01}
      ],
      "warnings": []
    }
  ],
  "warnings": []
}
```

- [ ] **Step 4: Run backend import tests**

Run: `pytest tests/test_inquiry_filters.py::test_import_draft_quote_sheet_parses_exported_template -q`

Expected: Pass.

### Task 3: Frontend Import Fill

**Files:**
- Modify: `static/js/app.js`
- Modify: `tests/test_frontend_special_approval.py`

- [ ] **Step 1: Write failing frontend import wiring test**

Assert that `importDraftQuoteSheet`, hidden file input creation, upload endpoint, and `applyImportedQuoteItems` exist.

```python
def test_frontend_import_quote_sheet_uploads_and_applies_items():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    assert "async function importDraftQuoteSheet" in source
    assert "/api/purchase-inquiries/draft/${id}/import-quote-sheet" in source
    assert "function applyImportedQuoteItems" in source
    assert "renderInquiryItems();" in source
```

- [ ] **Step 2: Run test and verify failure**

Run: `pytest tests/test_frontend_special_approval.py::test_frontend_import_quote_sheet_uploads_and_applies_items -q`

Expected: Fail because functions are not implemented.

- [ ] **Step 3: Implement import flow**

Add:

```javascript
async function importDraftQuoteSheet(id) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.xlsx';
    input.onchange = async () => {
        const file = input.files && input.files[0];
        if (!file) return;
        const formData = new FormData();
        formData.append('file', file);
        const res = await api(`/api/purchase-inquiries/draft/${id}/import-quote-sheet`, {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (!data.success) {
            showToast(data.message || '询比价导入失败', 'error');
            return;
        }
        applyImportedQuoteItems(data.items || []);
        const warningText = (data.warnings || []).join('；');
        showToast(warningText ? `询比价导入完成：${warningText}` : '询比价导入完成');
    };
    input.click();
}
```

Add:

```javascript
function applyImportedQuoteItems(items) {
    inquiryItems = (items || []).map(item => ({
        material_id: item.material_id || '',
        material_name: item.material_name || '',
        material_code: item.material_code || '',
        specification: item.specification || '',
        detail_spec: item.detail_spec || '',
        brand: item.brand || '',
        unit_name: item.unit_name || '',
        quantity: Number(item.quantity || 1),
        library_price: Number(item.library_price || 0),
        tax_price: Number(item.tax_price || 0),
        cash_price: Number(item.cash_price || 0),
        selected_quote_id: null,
        is_national_standard: item.is_national_standard,
        is_cash_price: item.is_cash_price || 0,
        import_warnings: item.warnings || [],
        quotes: item.quotes && item.quotes.length ? item.quotes : buildDefaultQuotes()
    }));
    renderInquiryItems();
    updateInquiryTotal();
}
```

- [ ] **Step 4: Run frontend tests**

Run: `pytest tests/test_frontend_special_approval.py -q`

Expected: Pass.

### Task 4: Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
pytest tests/test_frontend_special_approval.py tests/test_inquiry_filters.py -q
```

Expected: Pass.

- [ ] **Step 2: Run full tests**

Run:

```bash
pytest tests -q
```

Expected: Pass.

- [ ] **Step 3: Manual browser check**

Open the app, view a draft inquiry, confirm the toolbar shows:

`发布给供应商报价` `供应商报价入口` `询比价导出` `询比价导入`

Export the quote sheet, edit quantity/price in Excel, import it, and confirm inquiry detail rows update.

