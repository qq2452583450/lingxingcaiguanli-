from pathlib import Path


def test_frontend_hides_admin_approval_for_special_inquiries():
    source = Path("static/js/app.js").read_text(encoding="utf-8")

    assert "function isSpecialApprovalInquiry" in source
    assert "applicant_username" in source
    assert "wanglihua" in source
    assert "GX" in source
    assert "canApproveInquiry(i)" in source


def test_frontend_allows_approval_entry_for_unpublished_quote_status():
    source = Path("static/js/app.js").read_text(encoding="utf-8")

    assert "function isInquiryApprovalOpen" in source
    assert "报价未发布" in source
    assert "isInquiryApprovalOpen(i.approval_status)" in source


def test_frontend_draft_rows_do_not_include_export_quote_sheet_action():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    render_start = source.index("function renderDraftsTable")
    render_end = source.index("async function deleteInquiryDraft")
    render_drafts = source[render_start:render_end]

    assert "function exportDraftQuoteSheet" in source
    assert "/api/purchase-inquiries/draft/${id}/export-quote-sheet" in source
    assert "exportDraftQuoteSheet(${d.id})" not in render_drafts


def test_frontend_main_inquiry_rows_do_not_include_export_quote_sheet_action():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    render_start = source.index("function renderInquiryTable")
    render_end = source.index("function exportSupplierOrders")
    render_inquiries = source[render_start:render_end]

    assert "exportDraftQuoteSheet(${i.id})" not in render_inquiries


def test_frontend_inquiry_detail_toolbar_includes_export_and_import_quote_sheet_actions():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    view_start = source.index("async function viewInquiry")
    view_end = source.index("async function editInquiry")
    view_body = source[view_start:view_end]

    assert "i.approval_status === '草稿'" in source
    assert "exportDraftQuoteSheet(${i.id})" in view_body
    assert "importDraftQuoteSheet(${i.id})" in view_body


def test_frontend_import_quote_sheet_uploads_and_applies_items():
    source = Path("static/js/app.js").read_text(encoding="utf-8")

    assert "async function importDraftQuoteSheet" in source
    assert "/api/purchase-inquiries/draft/${id}/import-quote-sheet" in source
    assert "function applyImportedQuoteItems" in source
    assert "renderInquiryItems();" in source


def test_frontend_import_quote_sheet_keeps_lowest_quote_selected_for_submit():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    apply_start = source.index("function applyImportedQuoteItems")
    apply_end = source.index("async function deleteInquiryDraft")
    apply_body = source[apply_start:apply_end]

    assert "quotes[lowestIdx].is_selected = 1;" in apply_body
    assert "selected_quote_id: quotes[lowestIdx] && quotes[lowestIdx].is_selected ? quotes[lowestIdx].supplier_id : null" in apply_body
    assert "selected_quote_id: null" not in apply_body


def test_frontend_selected_quote_row_uses_yellow_background():
    source = Path("static/css/style.css").read_text(encoding="utf-8")

    assert ".quote-row.selected" in source
    assert "background: #fff3cd" in source
