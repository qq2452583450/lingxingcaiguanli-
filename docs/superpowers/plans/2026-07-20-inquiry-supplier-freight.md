# 询比价供应商整单运费 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在每家供应商的整张询比价报价中独立记录一笔含税运费，并以材料货款加运费进行整单比价、拟定和审批。

**Architecture:** 新建 `purchase_inquiry_supplier_freights` 表，将运费与询比价单、供应商唯一关联。后端集中生成供应商汇总并重算金额；管理端和供应商门户只编辑输入值、展示汇总值。旧单据缺少运费行时按零处理。

**Tech Stack:** Flask、SQLite、原生 JavaScript、openpyxl、pytest。

## Global Constraints

- 不改变材料 `tax_price`、`tax_exempt_price`、`total_amount` 的含义。
- 运费为非负含税金额，税率范围为 0 至 1，运费为 0 合法。
- 单据拟定供应商必须唯一且覆盖全部材料的有效报价。
- 历史单据没有运费数据时保持原金额。
- 只提交当前功能相关的代码、测试和设计文档。

---

### Task 1: 数据表与汇总接口

**Files:**
- Modify: `database/init_db.py`
- Modify: `blueprints/inquiries.py`
- Modify: `tests/test_inquiry_filters.py`

**Interfaces:**
- Produces: `get_inquiry_supplier_summaries(cursor, inquiry_id)`，返回 `supplier_id`、`goods_amount`、`tax_freight`、`tax_exempt_freight`、`freight_tax_rate`、`landed_total`。
- Produces: 单据详情响应的 `supplier_freights` 与 `supplier_summaries`。

- [ ] **Step 1: Write failing tests**

```python
def test_inquiry_detail_returns_supplier_freight_and_landed_total(client, test_db):
    # 两条材料货款合计 150，运费 20，详情返回到货总价 170。
    response = client.get(f'/api/purchase-inquiries/{inquiry_id}')
    assert response.get_json()['supplier_summaries'][0]['landed_total'] == 170
```

- [ ] **Step 2: Run the focused test and verify it fails because freight data is absent.**
- [ ] **Step 3: Create the freight table and migration check; implement summary query and detail response.**
- [ ] **Step 4: Run the focused test and verify it passes.**

### Task 2: 整单拟定与金额重算

**Files:**
- Modify: `blueprints/inquiries.py`
- Modify: `tests/test_inquiry_filters.py`

**Interfaces:**
- Consumes: `supplier_freights: [{supplier_id, tax_freight, tax_rate, remark}]`。
- Consumes: `selected_supplier_id`。
- Produces: `purchase_inquiries.total_amount = goods_amount + tax_freight`。

- [ ] **Step 1: Write failing tests**

```python
def test_create_inquiry_uses_selected_supplier_landed_total(client, test_db):
    response = client.post('/api/purchase-inquiries', json={
        'items': items,
        'selected_supplier_id': supplier_id,
        'supplier_freights': [{'supplier_id': supplier_id, 'tax_freight': 20, 'tax_rate': .13}],
    })
    assert fetch_inquiry(test_db, response.get_json()['id'])['total_amount'] == 170
```

- [ ] **Step 2: Run the focused tests and verify they fail because the new fields are ignored.**
- [ ] **Step 3: Persist normalized freight values, reject incomplete or mixed-supplier selection, and calculate server-side totals.**
- [ ] **Step 4: Run focused tests and verify they pass.**

### Task 3: 供应商门户整单运费

**Files:**
- Modify: `blueprints/supplier_portal.py`
- Modify: `supplier-portal.html`
- Modify: `static/js/supplier-portal.js`
- Modify: `tests/test_supplier_portal.py`

**Interfaces:**
- Produces: `GET /api/supplier/quote-requests/<inquiry_id>` 的 `freight` 字段。
- Produces: `PUT /api/supplier/quote-requests/<inquiry_id>/freight`，由登录供应商身份写入运费。

- [ ] **Step 1: Write failing API tests for supplier save, ownership rejection, and locked quote rejection.**
- [ ] **Step 2: Run tests and verify the freight endpoint is missing.**
- [ ] **Step 3: Add endpoint and render the freight input beneath the quote table; save it with the existing save action.**
- [ ] **Step 4: Run supplier portal tests and verify they pass.**

### Task 4: 管理端整单汇总与单供应商选择

**Files:**
- Modify: `static/js/app.js`
- Modify: `tests/test_frontend_structure.py`
- Modify: `tests/test_frontend_price_precision.py`

**Interfaces:**
- Consumes: `inquirySupplierFreights` and `supplier_summaries`。
- Produces: `selectInquirySupplier(supplierId)`，同步所有材料行的选定状态。

- [ ] **Step 1: Write failing static tests for freight summary rendering and one supplier selector.**
- [ ] **Step 2: Run tests and verify the new functions and labels are absent.**
- [ ] **Step 3: Render supplier summary panel, use landed total in the form total, and submit freight plus a single selected supplier.**
- [ ] **Step 4: Run frontend static tests and verify they pass.**

### Task 5: 导出、审批、对账与回归

**Files:**
- Modify: `blueprints/inquiries.py`
- Modify: `blueprints/reconciliation.py`
- Modify: `tests/test_inquiry_export_supplier_orders.py`
- Modify: `tests/test_inquiry_filters.py`

- [ ] **Step 1: Write failing export tests that expect goods total, freight, and landed total rows.**
- [ ] **Step 2: Run tests and verify exports do not contain freight rows.**
- [ ] **Step 3: Add freight rows to supplier orders and quote sheets; add a single freight detail to reconciliation data.**
- [ ] **Step 4: Run affected tests and the full `python -m pytest tests` suite.**

### Task 6: Review, integration and production release

**Files:**
- Modify: `docs/superpowers/specs/2026-07-20-inquiry-supplier-freight-design.md`
- Modify: `docs/superpowers/plans/2026-07-20-inquiry-supplier-freight.md`

- [ ] **Step 1: Inspect the final diff for mixed-supplier and historical-data regressions.**
- [ ] **Step 2: Run `python -m pytest tests`; expected result: all tests pass.**
- [ ] **Step 3: Commit only feature files on the isolated branch.**
- [ ] **Step 4: Merge into `dev`, push `dev`, then merge into and push `prod` to deploy.**
- [ ] **Step 5: Check the production deployment workflow result before reporting completion.**
