from pathlib import Path


def test_supplier_selection_only_updates_the_current_inquiry_item():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    function_source = source.split("function selectSupplierOption", 1)[1].split(
        "function toggleSupplierDropdown", 1
    )[0]

    assert "const quote = inquiryItems[itemIndex]?.quotes[quoteIndex]" in function_source
    assert "inquiryItems.length > 5" not in function_source
    assert "for (let i = 1; i < inquiryItems.length; i++)" not in function_source
