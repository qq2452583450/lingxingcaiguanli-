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
    assert "min-width: 0" in rules
    assert "white-space: normal !important" in rules
    assert "overflow-wrap: anywhere" in rules
    assert "overflow: hidden" not in rules
