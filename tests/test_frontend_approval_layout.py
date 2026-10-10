from pathlib import Path


def test_approval_modal_has_no_fixed_thousand_pixel_limit():
    html = Path("index.html").read_text(encoding="utf-8")
    modal = html.split('id="modal-approval"', 1)[1].split('<!-- 采购购物车', 1)[0]
    assert 'class="modal-content approval-modal-content"' in modal
    assert "max-width:1000px" not in modal


def test_approval_tables_wrap_without_hiding_quote_columns():
    css = Path("static/css/style.css").read_text(encoding="utf-8")
    rules = css.split("/* Approval comparison", 1)[1].split("/* ============ Forms", 1)[0]
    assert "width: calc(100vw - 24px)" in rules
    assert "max-width: none" in rules
    assert "table-layout: fixed" in rules
    assert "min-width: 0 !important" in rules
    assert "white-space: normal !important" in rules
    assert "overflow-wrap: anywhere" in rules
    assert "overflow: hidden" not in rules


def test_inquiry_detail_shares_wide_wrapping_layout_only_for_inquiries():
    js = Path("static/js/app.js").read_text(encoding="utf-8")
    view = js.split("async function viewInquiry(id)", 1)[1].split("async function editInquiry", 1)[0]
    assert 'class="card inquiry-detail-info"' in view
    assert 'class="table-container inquiry-detail-table"' in view
    assert "modal.classList.toggle('inquiry-detail-modal', !!modal.querySelector('.inquiry-detail-info'))" in js
    css = Path("static/css/style.css").read_text(encoding="utf-8")
    assert "#modal-detail.inquiry-detail-modal .modal-content" in css
    assert "#modal-detail .inquiry-detail-table table" in css
