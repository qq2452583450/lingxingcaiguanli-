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
    assert "发票、收据或相关单据" in index_source
    assert "loadPettyCash" in app_source
    assert "/api/petty-cash/loans" in app_source
    assert "/api/petty-cash/usages" in app_source

