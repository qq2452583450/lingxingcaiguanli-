from pathlib import Path


def test_frontend_supports_guangxi_material_region():
    app_source = Path("static/js/app.js").read_text(encoding="utf-8")
    index_source = Path("index.html").read_text(encoding="utf-8")

    assert "'GX': '广西'" in app_source
    assert '<option value="GX">广西</option>' in index_source
