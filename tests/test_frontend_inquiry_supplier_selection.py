from pathlib import Path


def test_supplier_selection_only_updates_the_current_inquiry_item():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    function_source = source.split("function selectSupplierOption", 1)[1].split(
        "function toggleSupplierDropdown", 1
    )[0]

    assert "const quote = inquiryItems[itemIndex]?.quotes[quoteIndex]" in function_source
    assert "inquiryItems.length > 5" not in function_source
    assert "for (let i = 1; i < inquiryItems.length; i++)" not in function_source


def test_quote_selection_does_not_select_the_same_supplier_for_every_material():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    function_source = source.split("function selectQuote", 1)[1].split(
        "function updateQuoteSupplier", 1
    )[0]

    assert "selectInquirySupplier" not in function_source
    assert "item.quotes.forEach(q => q.is_selected = false)" in function_source
    assert "item.quotes[quoteIndex].is_selected = true" in function_source
