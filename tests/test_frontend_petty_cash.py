from pathlib import Path


def test_frontend_has_independent_petty_cash_module():
    index_source = Path("index.html").read_text(encoding="utf-8")
    app_source = Path("static/js/app.js").read_text(encoding="utf-8")

    assert 'data-module="petty_cash"' in index_source
    assert 'id="petty_cashModule"' in index_source
    assert "备用金管理" in index_source
    assert "借款总额" in index_source
    assert "现有金额" in index_source
    assert "使用情况" in index_source
    assert "票据" in index_source
    assert "供应商名称" in index_source
    assert "材料名称" in index_source
    assert "发票金额" in index_source
    assert "发票类型" in index_source
    assert "运费" in index_source
    assert "宽带费" in index_source
    assert "零星材" in index_source
    assert "生活类费用" in index_source
    assert "极小金额零星材购买" not in index_source
    assert "<th>明细单号</th>" not in index_source
    assert "<th>备用金单号</th>" not in index_source
    assert 'name="proof_files"' in index_source
    assert "multiple" in index_source
    assert "loadPettyCash" in app_source
    assert "/api/petty-cash/loans" in app_source
    assert "/api/petty-cash/usages" in app_source
    assert "显示附件" in app_source
    assert "proof_file_count" in app_source
    assert "canManagePettyCash" in app_source
    assert "supplier_name" in app_source
    assert "material_name" in app_source
    assert "invoice_amount" in app_source
    assert "invoice_type" in app_source

