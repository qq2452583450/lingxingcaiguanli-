"""Exercise the actual detail and approval JS with unselected lowest quotes."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_detail_and_approval_only_include_nominated_quotes():
    node = shutil.which('node')
    if not node:
        bundled = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
        node = str(bundled) if bundled.exists() else None
    if not node:
        pytest.skip('Node runtime unavailable')
    script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('static/js/app.js','utf8');
const detail = 'async function viewInquiry'+source.split('async function viewInquiry')[1].split('async function editInquiry')[0];
const approval = 'async function approveInquiry'+source.split('async function approveInquiry')[1].split('async function submitApproval')[0];
(async()=>{
for(const selected of [false,true]){
 const elements = new Map();
 const element=id=>{if(!elements.has(id))elements.set(id,{style:{},classList:{add:()=>{},remove:()=>{}},innerHTML:'',textContent:''});return elements.get(id);};
 const data={success:true,legacy:false,data:{id:7,inquiry_no:'TEST',total_amount:0,approval_status:'已同意'},
 items:[{quantity:140,quotes:[{supplier_id:11,tax_price:120,is_lowest:1,is_selected:selected?1:0}]}],
 supplier_freights:[{supplier_id:11,tax_freight:99}]};
 const context={console,Set,Promise,window:{},isInquiryApprovalOpen:()=>false,isSpecialApprovalInquiry:()=>false,currentUser:{id:1,role_name:'系统管理员'},
 document:{getElementById:element},api:async url=>({json:async()=>url.endsWith('/approval-history')?{success:true,data:[]}:data}),
 escapeHtml:x=>String(x??''),getStatusClass:()=>'',renderMergedDetailTable:()=>'',openModal:()=>{},
 showToast:msg=>{throw Error(msg);}};
 vm.createContext(context);vm.runInContext(detail+'\n'+approval,context);
 await context.viewInquiry(7);
 const amount=selected?'16899.00':'0.00';
 assert(element('detailContent').innerHTML.includes('<strong>总金额:</strong> ¥'+amount));
 await context.approveInquiry(7);
 assert.strictEqual(element('approvalTotalAmount').textContent,'¥'+amount);
 assert.strictEqual(element('approvalFreightAmount').textContent,selected?'¥99.00':'¥0.00');
}
console.log(JSON.stringify({passed:2}));
})().catch(e=>{console.error(e);process.exit(1);});
'''
    result = subprocess.run([node, '-e', script], text=True, capture_output=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['passed'] == 2
