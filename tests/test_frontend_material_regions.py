from pathlib import Path


def test_frontend_supports_guangxi_material_region():
    app_source = Path("static/js/app.js").read_text(encoding="utf-8")
    index_source = Path("index.html").read_text(encoding="utf-8")

    assert "'GX': '广西'" in app_source
    assert '<option value="GX">广西</option>' in index_source


def test_material_export_button_uses_active_material_filters():
    app_source = Path("static/js/app.js").read_text(encoding="utf-8")
    index_source = Path("index.html").read_text(encoding="utf-8")

    assert 'onclick="exportMaterials()"' in index_source
    function_source = app_source.split("function exportMaterials", 1)[1].split(
        "// 加载更多材料", 1
    )[0]
    assert "filter_name" in function_source
    assert "filter_spec" in function_source
    assert "filter_brand" in function_source
    assert "filter_region" in function_source
    assert "window.location.href = `/api/materials/export?${params.toString()}`" in function_source
