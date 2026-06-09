from pathlib import Path


def test_frontend_supports_supplier_password_change_and_special_project_skip():
    app_source = Path("static/js/app.js").read_text(encoding="utf-8")
    index_source = Path("index.html").read_text(encoding="utf-8")

    assert "must_change_password" in app_source
    assert "showForcePasswordChange" in app_source
    assert "isAllBoundProjectsUser" in app_source
    assert "leikefeng" in app_source
    assert "tanxiang" in app_source
    assert "modal-force-password-change" in index_source
