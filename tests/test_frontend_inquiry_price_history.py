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


def test_quote_tax_rate_rendering_and_both_flatten_paths():
    node = shutil.which('node') or str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
    script = r'''
const vm = require('vm'), fs = require('fs'), assert = require('assert');
const js = fs.readFileSync('static/js/app.js', 'utf8');
const context = {escapeHtml: value => String(value ?? ''), renderInquiryHistoricalPrice: () => '-', renderInquirySupplierFreightSummary: () => ''};
vm.createContext(context);
vm.runInContext(js.slice(js.indexOf('function formatInquiryQuoteTaxRate('), js.indexOf('// 辅助函数：格式化是否国标')), context);
vm.runInContext(js.slice(js.indexOf('function renderMergedDetailTable('), js.indexOf('function renderInquirySupplierFreightSummary(')), context);
for (const [rate,label] of [[0.13,'税率 13%'],[0.01,'税率 1%'],[0,'税率 0%'],[0.015,'税率 1.5%'],[null,'税率未记录'],['','税率未记录']]) {
 const html = context.renderMergedDetailTable([{material_id:1, supplier_name:'供应商', supplier_tax_rate:0.09, tax_rate:rate, quantity:2, this_price:10}]);
 assert(html.includes('inquiry-quote-tax-rate'), html);
 assert(html.includes(label), html);
 assert(html.includes('供应商库税率 9%'), html);
}
assert.equal((js.match(/supplier_tax_rate: q.supplier_tax_rate \?\? null,/g) || []).length, 2);
'''
    subprocess.run([node, '-e', script], check=True, capture_output=True, text=True)
