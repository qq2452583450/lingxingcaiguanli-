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


def test_supplier_management_shows_generated_account_name_not_status():
    app_source = Path("static/js/app.js").read_text(encoding="utf-8")
    index_source = Path("index.html").read_text(encoding="utf-8")

    assert "<th>账号</th>" in index_source
    assert "s.account_username" in app_source
    assert "账号状态" not in index_source
    assert "账号状态" not in app_source
    assert "初始密码：888888" in app_source
