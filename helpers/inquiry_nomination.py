"""Default nomination follows the inquiry's existing ex-tax price comparison."""
import math


def lowest_priced_quote(quotes):
    candidates = []
    for index, quote in enumerate(quotes or []):
        price = float(quote.get('tax_price') or 0)
        if not quote.get('supplier_id') or not math.isfinite(price) or price <= 0:
            continue
        rate = float(quote.get('tax_rate') if quote.get('tax_rate') is not None else 0.13)
        ex_price = float(quote.get('tax_exempt_price') or price / (1 + rate))
        if math.isfinite(ex_price) and ex_price > 0:
            candidates.append((ex_price, index, quote))
    return min(candidates, key=lambda entry: entry[:2])[2] if candidates else None


def default_item_nominations(items):
    for item in items:
        if item.get('selected_quote_id'):
            continue
        quotes = item.get('quotes', [])
        selected = next((q for q in quotes if q.get('is_selected') and q.get('supplier_id')), None)
        selected = selected or lowest_priced_quote(quotes)
        if selected:
            item['selected_quote_id'] = selected['supplier_id']
