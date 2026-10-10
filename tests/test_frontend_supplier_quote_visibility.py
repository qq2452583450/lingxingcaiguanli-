from pathlib import Path


def test_supplier_online_quote_controls_are_not_rendered_in_inquiry_details():
    js = Path("static/js/app.js").read_text(encoding="utf-8")
    view = js.split("async function viewInquiry(id)", 1)[1].split("async function editInquiry", 1)[0]
    for text in ("发布给供应商报价", "锁定报价", "供应商报价入口", "/supplier-portal", "报价状态", "供应商无法修改", "publishQuotes(", "lockQuotes("):
        assert text not in view
    for text in ("询比价导出", "询比价导入", "renderMergedDetailTable", "detailFreightTotal", "inquiry-detail-info"):
        assert text in view


def test_inquiry_list_preserves_approval_but_removes_online_quote_status():
    js = Path("static/js/app.js").read_text(encoding="utf-8")
    table = js.split("function renderInquiryTable(inquiries)", 1)[1].split("function renderMergedDetailTable", 1)[0]
    assert "quote_status" not in table
    assert "approval_status" in table
    assert 'colspan="8"' in table
    html = Path("index.html").read_text(encoding="utf-8")
    assert "<th>报价状态</th>" not in html
