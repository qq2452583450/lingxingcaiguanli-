import re
from pathlib import Path


def test_each_nav_module_has_matching_page_container():
    html = Path("index.html").read_text(encoding="utf-8")
    modules = set(re.findall(r'data-module="([^"]+)"', html))

    missing = [
        module for module in sorted(modules)
        if f'id="{module}Module"' not in html
    ]

    assert missing == []


def test_material_table_shows_latest_purchase_columns_before_actions():
    html = Path("index.html").read_text(encoding="utf-8")
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    table = html[html.index('<table id="materialTableEl">'):html.index('<tbody id="materialTable">')]

    assert table.index("供应商") < table.index("最后采购项目")
    assert table.index("最后采购项目") < table.index("最后采购时间")
    assert table.index("最后采购时间") < table.index("操作")
    assert "m.last_purchase_project" in source
    assert "m.last_purchase_time" in source


def test_material_price_history_is_available_from_both_tax_inclusive_prices():
    html = Path("index.html").read_text(encoding="utf-8")
    source = Path("static/js/app.js").read_text(encoding="utf-8")

    assert 'id="modal-material-price-history"' in html
    assert "openMaterialPriceHistory(${m.id}, 'tax')" in source
    assert "openMaterialPriceHistory(${m.id}, 'cash')" in source
    assert "/api/materials/${materialId}/price-history" in source


def test_new_inquiry_from_material_selection_defaults_to_normal_tax_price():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    start = source.index("async function generateInquiryFromSelection()")
    end = source.index("function saveCartToStorage()", start)
    selected_inquiry_source = source[start:end]

    assert "is_cash_price: 0," in selected_inquiry_source
    assert "is_cash_price: m.is_cash_price || 0" not in selected_inquiry_source
