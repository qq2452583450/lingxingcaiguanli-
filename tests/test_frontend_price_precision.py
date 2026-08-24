from pathlib import Path


def _function_body(source, name):
    marker = f"function {name}("
    start = source.index(marker)
    brace_start = source.index("{", start)
    depth = 0
    for pos in range(brace_start, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[brace_start + 1:pos]
    raise AssertionError(f"Function {name} body not found")


def test_quote_tax_exempt_display_does_not_rewrite_tax_price_input():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    render_body = _function_body(source, "renderInquiryItems")
    update_body = _function_body(source, "updateQuoteField")

    exempt_input_start = render_body.index('class="quote-tax-exempt"')
    exempt_input_end = render_body.index('placeholder="0.00" readonly', exempt_input_start)
    exempt_input_markup = render_body[exempt_input_start:exempt_input_end]

    assert "onchange=" not in exempt_input_markup
    assert "taxPriceInput.value" not in update_body


def test_quote_tax_price_precision_is_preserved_when_editing():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    update_body = _function_body(source, "updateQuoteField")
    live_body = _function_body(source, "updateQuoteFieldLive")

    assert "quote.tax_price = roundMoney(numValue)" not in update_body
    assert "quote.tax_price = roundMoney(numValue)" not in live_body


def test_quote_tax_price_input_accepts_four_decimal_precision():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    render_body = _function_body(source, "renderInquiryItems")

    tax_price_input_start = render_body.index('oninput="updateQuoteFieldLive')
    tax_price_input_markup_start = render_body.rindex("<input", 0, tax_price_input_start)
    tax_price_input_markup_end = render_body.index(">", tax_price_input_start)
    tax_price_input_markup = render_body[tax_price_input_markup_start:tax_price_input_markup_end]

    assert 'step="0.0001"' in tax_price_input_markup


def test_manual_quote_payload_rounds_tax_price_before_save_or_submit():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    submit_body = _function_body(source, "submitInquiryForm")
    draft_body = _function_body(source, "saveInquiryDraft")

    assert "tax_price: normalizeManualQuoteMoney(q.tax_price)" in submit_body
    assert "tax_exempt_price: normalizeManualQuoteMoney(q.tax_exempt_price)" in submit_body
    assert "tax_price: normalizeManualQuoteMoney(q.tax_price)" in draft_body
    assert "tax_exempt_price: normalizeManualQuoteMoney(q.tax_exempt_price)" in draft_body


def test_manual_quote_input_formats_float_tail_for_display():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    render_body = _function_body(source, "renderInquiryItems")

    assert 'value="${formatManualQuoteInputValue(quote.tax_price)}"' in render_body


def test_inquiry_form_uses_selected_supplier_freights_and_landed_total():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    submit_body = _function_body(source, "submitInquiryForm")

    assert "renderInquirySupplierSummary" in source
    assert "已拟定供应商汇总" in source
    assert "supplier_freights" in submit_body
    assert "selected_supplier_id: null" in submit_body


def test_inquiry_detail_table_displays_supplier_freight_and_landed_total():
    source = Path("static/js/app.js").read_text(encoding="utf-8")

    assert "function renderMergedDetailTable" in source
    assert "return html + renderInquirySupplierFreightSummary(flatDetails, options);" in source
    assert "function renderInquirySupplierFreightSummary" in source
    assert "运费明细（按供应商）" in source
    assert "approvalFreightAmount" in source
    assert "<p><strong>运费:</strong>" in source
    assert "supplierSummaries: data.supplier_summaries" in source
    assert "supplierFreights: data.supplier_freights" in source
    assert "tax_freight" in source
    assert "landed_total" in source


def test_cart_generated_inquiry_refreshes_library_price_after_material_cache_loads():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    cart_body = _function_body(source, "generateInquiryFromCart")
    sync_body = _function_body(source, "syncCartInquiryItemsWithMaterialCache")

    assert "function syncCartInquiryItemsWithMaterialCache()" in source
    assert "syncCartInquiryItemsWithMaterialCache();" in cart_body
    assert "item.tax_price = material.tax_price || 0;" in sync_body
    assert "item.library_price = item.is_cash_price === 1 ? item.cash_price : item.tax_price;" in sync_body
