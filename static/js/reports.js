// Reports always render/export the last applied filters, not unsubmitted edits.
let reportFilters = null;
let reportOptions = null;
let reportPages = {};
let reportRequest = 0;
let reportCurrentKind = 'purchase';
let reportExporting = false;
let reportActiveTableKey = 'projects';

function reportEscape(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function reportFormat(value, type) {
    if (value === null || value === undefined || value === '') return '—';
    if (type === 'text') return reportEscape(value);
    return Number(value).toLocaleString('zh-CN', {minimumFractionDigits:type === 'money' ? 2 : 0, maximumFractionDigits:type === 'money' ? 2 : 4});
}

async function reportJson(url) {
    const response = await api(url);
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.message || '报表加载失败');
    return data.data;
}

function reportDateText(d) {
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

async function loadReportCenter() {
    ++reportRequest;
    const root = document.getElementById('reportCenter');
    root.innerHTML = '<div class="card">正在加载报表…</div>';
    // Reset between openings so a different signed-in user never sees stale filters/options.
    reportFilters = null;
    reportPages = {};
    try {
        reportOptions = await reportJson('/api/reports/options');
        const optionList = (rows, label) => rows.map(r => `<option value="${Number(r.id)}">${reportEscape(r[label])}</option>`).join('');
        root.innerHTML = `
            <div class="report-tabs" role="group" aria-label="报表类型">${reportOptions.reports.map(r => `<button type="button" class="btn btn-secondary" data-report-kind="${r.key}" onclick="reportSwitch('${r.key}')">${reportEscape(r.title)}</button>`).join('')}</div>
            <div class="card"><form id="reportFilterForm" class="report-filters" onsubmit="event.preventDefault(); reportApply();">
                <label>开始日期<input type="date" id="reportStart" required></label>
                <label>结束日期<input type="date" id="reportEnd" required></label>
                <label>项目<select id="reportProject"><option value="">全部授权项目</option>${optionList(reportOptions.projects,'project_name')}</select></label>
                <label>供应商<select id="reportSupplier"><option value="">全部供应商</option>${optionList(reportOptions.suppliers,'supplier_name')}</select></label>
                <label>材料名称 / 规格<input type="search" id="reportKeyword" placeholder="输入材料关键词"></label>
                <label>单位<select id="reportUnit"><option value="">全部单位</option>${reportOptions.units.map(u => `<option>${reportEscape(u)}</option>`).join('')}</select></label>
                <button class="btn btn-primary" type="submit">查询统计</button>
                <button class="btn btn-secondary" type="button" onclick="reportPreset('month')">本月</button>
                <button class="btn btn-secondary" type="button" onclick="reportPreset('last')">上月</button>
                <button class="btn btn-secondary" type="button" onclick="reportReset()">重置</button>
                <button id="reportExportButton" class="btn btn-secondary" type="button" onclick="reportExport()" disabled>导出全部 Excel</button>
            </form></div><div id="reportResults" aria-live="polite"></div>`;
        reportPreset('month', false);
        if (reportOptions.projects.some(p => p.id === currentProjectId)) document.getElementById('reportProject').value = currentProjectId;
        reportSwitch(reportCurrentKind);
    } catch (error) {
        root.innerHTML = `<div class="report-error">${reportEscape(error.message)} <button class="btn btn-secondary" onclick="loadReportCenter()">重新加载</button></div>`;
    }
}

function reportPreset(which, apply = true) {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth()-(which === 'last' ? 1 : 0), 1);
    const end = which === 'last' ? new Date(now.getFullYear(), now.getMonth(), 0) : now;
    document.getElementById('reportStart').value = reportDateText(start);
    document.getElementById('reportEnd').value = reportDateText(end);
    if (apply) reportApply();
}

function reportReset() {
    for (const name of ['Project','Supplier','Keyword','Unit']) document.getElementById('report'+name).value = '';
    reportPreset('month');
}

function reportSwitch(kind) {
    if (kind !== reportCurrentKind) reportActiveTableKey = 'projects';
    reportCurrentKind = kind;
    const snapshot = ['inventory','base_inventory'].includes(kind);
    for (const id of ['reportStart','reportEnd']) document.getElementById(id).disabled = snapshot;
    const supplier = document.getElementById('reportSupplier');
    supplier.disabled = !['purchase','stock_in'].includes(kind);
    const unit = document.getElementById('reportUnit');
    unit.disabled = kind === 'cash';
    document.querySelectorAll('[data-report-kind]').forEach(button => {
        button.className = `btn ${button.dataset.reportKind === kind ? 'btn-primary' : 'btn-secondary'}`;
        button.setAttribute('aria-pressed', String(button.dataset.reportKind === kind));
    });
    reportApply();
}

function reportApply() {
    const form = document.getElementById('reportFilterForm');
    if (!form.reportValidity()) return;
    const value = name => document.getElementById('report'+name).value;
    if (value('Start') > value('End')) { showToast('开始日期不能晚于结束日期', 'error'); return; }
    reportFilters = {kind:reportCurrentKind, start_date:value('Start'), end_date:value('End'), project_id:value('Project'),
        supplier_id:document.getElementById('reportSupplier').disabled ? '' : value('Supplier'), keyword:value('Keyword').trim(),
        unit:document.getElementById('reportUnit').disabled ? '' : value('Unit')};
    reportPages = {};
    reportLoad();
}

async function reportLoad() {
    const requestId = ++reportRequest;
    const area = document.getElementById('reportResults');
    document.getElementById('reportExportButton').disabled = true;
    area.innerHTML = '<div class="card">正在统计全部符合条件的记录…</div>';
    try {
        const params = new URLSearchParams({...reportFilters, ...reportPages});
        const data = await reportJson('/api/reports?' + params);
        if (requestId !== reportRequest) return;
        if (!data.tables.some(t => t.key === reportActiveTableKey)) reportActiveTableKey = data.tables[0].key;
        const applied = data.filters;
        const projectLabel = reportOptions.projects.find(p => String(p.id) === String(applied.project_id))?.project_name || '全部授权项目';
        const supplierLabel = reportOptions.suppliers.find(s => String(s.id) === String(applied.supplier_id))?.supplier_name;
        const period = ['inventory','base_inventory'].includes(applied.kind) ? '当前库存快照' : `${applied.start_date} 至 ${applied.end_date}`;
        const filterLabel = [period,projectLabel,supplierLabel,applied.keyword && '材料：'+applied.keyword,applied.unit && '单位：'+applied.unit].filter(Boolean).join(' · ');
        area.innerHTML = `<div class="report-meta">已应用：${reportEscape(filterLabel)}<br>${reportEscape(data.generated_at)} 统计 · 每表每页 50 条，导出包含全部结果</div>
            <div class="report-kpis">${data.summary.map(([label,value,type]) => `<div class="report-kpi"><span>${reportEscape(label)}${type === 'money' ? '（元）' : ''}</span><strong>${reportFormat(value,type)}</strong></div>`).join('')}</div>
            <details class="report-notes"><summary>统计口径与范围（点击展开）</summary>${data.notes.map(n => `<div>${reportEscape(n)}</div>`).join('')}</details>
            <div class="report-views" role="group" aria-label="统计视图">${data.tables.map(t => `<button class="btn ${t.key === reportActiveTableKey ? 'btn-primary' : 'btn-secondary'}" data-report-view="${t.key}" aria-pressed="${t.key === reportActiveTableKey}" onclick="reportSelectTable('${t.key}')">${reportEscape(t.title)}（${t.total}）</button>`).join('')}</div>
            ${data.tables.map(reportRenderTable).join('')}`;
        document.getElementById('reportExportButton').disabled = reportExporting;
    } catch (error) {
        if (requestId !== reportRequest) return;
        area.innerHTML = `<div class="report-error">${reportEscape(error.message)} <button class="btn btn-secondary" onclick="reportLoad()">重试</button></div>`;
    }
}

function reportRenderTable(table) {
    const chart = table.page === 1 && ['projects','supplier_counts','supplier_amounts'].includes(table.key);
    const metric = table.key === 'supplier_counts' ? 'count' : 'amount';
    const largest = Math.max(1, ...table.rows.slice(0,10).map(r => Number(r[metric])));
    const bars = chart && table.rows.length ? `<div class="report-bars" aria-label="前十名概览">${table.rows.slice(0,10).map(r => `<div class="report-bar"><span>${reportEscape(r.project_name || r.supplier_name)}</span><div class="report-bar-track"><div class="report-bar-fill" style="width:${Math.max(0,Number(r[metric]))/largest*100}%"></div></div><span class="report-bar-value">${reportFormat(r[metric],metric === 'count' ? 'number' : 'money')}${metric === 'count' ? ' 笔' : ' 元'}</span></div>`).join('')}</div>` : '';
    return `<section class="card${table.key === reportActiveTableKey ? '' : ' hidden'}" data-report-table="${table.key}" id="reportTable-${table.key}">
        <div class="report-table-header"><h3>${reportEscape(table.title)}</h3><span>共 ${table.total} 条${chart ? ' · 图示前 10 名' : ''}</span></div>${bars}
        <div class="table-container"><table><thead><tr>${table.columns.map(c => `<th${c.type !== 'text' ? ' class="report-number"' : ''}>${reportEscape(c.label)}</th>`).join('')}</tr></thead>
        <tbody>${table.rows.length ? table.rows.map(r => `<tr>${table.columns.map(c => `<td${c.type !== 'text' ? ' class="report-number"' : ''}>${reportFormat(r[c.key],c.type)}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${table.columns.length}" style="text-align:center;padding:24px">当前筛选条件下暂无记录</td></tr>`}</tbody></table></div>
        <div class="report-pager"><span>第 ${table.page} / ${table.pages} 页 · 每页 50 条</span><div><button class="btn btn-secondary" ${table.page <= 1 ? 'disabled' : ''} onclick="reportPage('${table.key}',${table.page-1})">上一页</button> <button class="btn btn-secondary" ${table.page >= table.pages ? 'disabled' : ''} onclick="reportPage('${table.key}',${table.page+1})">下一页</button></div></div></section>`;
}

function reportSelectTable(key) {
    reportActiveTableKey = key;
    document.querySelectorAll('[data-report-table]').forEach(section => section.classList.toggle('hidden', section.dataset.reportTable !== key));
    document.querySelectorAll('[data-report-view]').forEach(button => {
        button.className = `btn ${button.dataset.reportView === key ? 'btn-primary' : 'btn-secondary'}`;
        button.setAttribute('aria-pressed', String(button.dataset.reportView === key));
    });
}

async function reportPage(key, page) {
    reportPages['page_'+key] = page;
    await reportLoad();
    document.getElementById('reportTable-'+key)?.scrollIntoView({block:'start'});
}

async function reportExport() {
    if (!reportFilters || reportExporting) return;
    reportExporting = true;
    const button = document.getElementById('reportExportButton');
    button.disabled = true;
    button.textContent = '正在生成…';
    const filters = {...reportFilters};
    try {
        const response = await api('/api/reports/export?' + new URLSearchParams(filters));
        if (!response.ok || (response.headers.get('Content-Type') || '').includes('json')) {
            const data = await response.json(); throw new Error(data.message || '导出失败');
        }
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement('a');
        link.href = url;
        const title = reportOptions.reports.find(r => r.key === filters.kind).title;
        link.download = `${title}_${filters.start_date}_${filters.end_date}.xlsx`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (error) { showToast(error.message, 'error'); }
    finally { reportExporting = false; button.disabled = false; button.textContent = '导出全部 Excel'; }
}
