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
