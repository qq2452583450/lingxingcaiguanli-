from pathlib import Path


def test_first_material_supplier_selection_synchronizes_the_same_quote_column():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    function_source = source.split("function selectSupplierOption", 1)[1].split(
        "function toggleSupplierDropdown", 1
    )[0]

    assert "const quote = inquiryItems[itemIndex]?.quotes[quoteIndex]" in function_source
    assert "itemIndex === 0" in function_source
    assert "syncSupplierFromFirstInquiryItem(quoteIndex, supplierId, supplierName)" in function_source
    assert "for (let itemIndex = 1; itemIndex < inquiryItems.length; itemIndex++)" in function_source
    assert "inquiryItems[itemIndex]?.quotes?.[quoteIndex]" in function_source


def test_supplier_selection_on_later_material_does_not_sync_backwards():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    function_source = source.split("function selectSupplierOption", 1)[1].split(
        "function toggleSupplierDropdown", 1
    )[0]

    assert "const syncedFollowingItems = itemIndex === 0" in function_source
    assert "syncSupplierFromFirstInquiryItem(quoteIndex, supplierId, supplierName)" in function_source


def test_quote_selection_does_not_select_the_same_supplier_for_every_material():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    function_source = source.split("function selectQuote", 1)[1].split(
        "function updateQuoteSupplier", 1
    )[0]

    assert "selectInquirySupplier" not in function_source
    assert "item.quotes.forEach(q => q.is_selected = false)" in function_source
    assert "item.quotes[quoteIndex].is_selected = true" in function_source
    assert "renderInquiryItems();" in function_source
