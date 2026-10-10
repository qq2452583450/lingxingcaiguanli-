"""Execute price-cell rendering and check the provenance link is safe and usable."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_historical_price_cells_show_sources_candidates_and_reasons():
    node = shutil.which('node')
    if not node:
        bundled = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
        node = str(bundled) if bundled.exists() else None
    if not node:
        pytest.skip('Node runtime unavailable')
    script = r'''
const vm = require('vm'), fs = require('fs'), assert = require('assert');
const context = {escapeHtml: value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;')};
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/js/inquiry-price-history.js', 'utf8'), context);
const row = {historical_lowest_price:29,historical_price_inquiry_id:7,historical_price_item_id:3,
 historical_price_source:{match_type:'等价规格匹配'},historical_price_candidates:[{}]};
const cell = context.renderInquiryHistoricalPrice(row);
assert(cell.includes('¥29.00'));
assert(cell.includes('等价规格匹配'));
assert(cell.includes('1条待核对'));
assert(cell.includes('openInquiryPriceHistory(7, 3, false)'));
const none = context.renderInquiryHistoricalPrice({...row,historical_lowest_price:null,historical_price_source:null,
 historical_price_reason:'<img src=x onerror=bad()>',historical_price_legacy:true});
assert(none.includes('未匹配'));
assert(!none.includes('<img'));
assert(none.includes('openInquiryPriceHistory(7, 3, true)'));
'''
    subprocess.run([node, '-e', script], check=True, capture_output=True, text=True)


def test_view_and_approval_preserve_price_context_for_every_quote():
    js = Path('static/js/app.js').read_text(encoding='utf-8')
    assert js.count('historical_price_context: item,') == 4
    html = Path('index.html').read_text(encoding='utf-8')
    assert html.index('/static/js/inquiry-price-history.js') < html.index('/static/js/app.js')
