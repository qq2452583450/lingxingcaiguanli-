// Historical price identity review. All matches and permissions come from the server.
let inquiryPriceReview = null;

function renderInquiryHistoricalPrice(row) {
    const source = row.historical_price_source;
    const price = row.historical_lowest_price;
    const amount = price == null ? '未匹配' : '¥' + Number(price).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
    const label = source ? source.match_type : (row.historical_price_reason || '无可比历史记录');
    const count = (row.historical_price_candidates || []).length;
    if (!row.historical_price_item_id) return escapeHtml(amount);
    return `<button type="button" class="price-history-link inquiry-price-link"
        onclick="openInquiryPriceHistory(${Number(row.historical_price_inquiry_id)}, ${Number(row.historical_price_item_id)}, ${row.historical_price_legacy ? 'true' : 'false'})">
        ${escapeHtml(amount)}</button><small>${escapeHtml(label)}</small>
        ${count ? `<small class="price-review-pending">${count}条待核对</small>` : ''}`;
}

async function openInquiryPriceHistory(inquiryId, itemId, legacy = false) {
    let modal = document.getElementById('modal-inquiry-price-history');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'modal-inquiry-price-history';
        modal.className = 'modal inquiry-price-review-modal';
        modal.innerHTML = `<div class="modal-content inquiry-price-review-content">
            <div class="modal-header"><h2>历史最低价来源与规格核对</h2>
            <button type="button" class="modal-close" onclick="closeModal('modal-inquiry-price-history')">×</button></div>
            <div id="inquiryPriceReviewBody"></div></div>`;
        document.body.appendChild(modal);
    }
    openModal(modal.id);
    const body = document.getElementById('inquiryPriceReviewBody');
    body.textContent = '正在查询历史审批价格…';
    try {
        const url = `/api/purchase-inquiries/${inquiryId}/price-history/${itemId}${legacy ? '?legacy=1' : ''}`;
        const response = await api(url);
        const result = await response.json();
        if (!response.ok || !result.success) throw new Error(result.message || '查询失败');
        inquiryPriceReview = { url, inquiryId, itemId, legacy, ...result };
        renderInquiryPriceReview();
    } catch (error) {
        inquiryPriceReview = null;
        body.textContent = error.message;
    }
}

function renderInquiryPriceReview() {
    const { data: row, can_confirm: canConfirm } = inquiryPriceReview;
    const current = row.historical_price_current_description;
    const e = escapeHtml;
    const money = price => '¥' + Number(price).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
    const currentText = [current.material_name, current.specification, current.detail_spec, current.brand, current.unit_name].filter(Boolean).join(' / ');
    const parameters = values => Object.entries(values || {}).map(([name, value]) => e(name) + '：' + e(value) + 'mm').join('，') || '未识别完整的带标签参数，按原规格保守核对';
    const renderRows = (histories, pending) => histories.map((h, index) => `<tr>
        <td>${e(h.inquiry_date || '-')}<br>${e(h.inquiry_no)}<br>${e(h.project_name || '-')}</td>
        <td>${e(h.supplier_name || '-')}<br>${money(h.price)}<br>税率：${h.tax_rate == null ? '旧记录未记录' : e(safeRate(h.tax_rate))}<br>${e(h.price_basis)}</td>
        <td>${e(h.material_code)}<br>${e(h.specification || '未记录')}<br>${e(h.detail_spec || '未记录')}<br>${e(h.brand || '品牌未记录')} / ${e(h.unit_name || '单位未记录')}<br>${parameters(h.key_parameters)}<br><small>${e(h.parameter_source)}</small></td>
        <td>${e(h.match_type)}${h.confirmed_name ? `<br>确认人：${e(h.confirmed_name)}<br>${e(h.confirmation_reason)}` : ''}
        ${canConfirm && pending ? `<button type="button" class="btn btn-primary btn-sm" onclick="updateInquiryPriceMatch('confirm', ${index})">确认同规格</button>` : ''}
        ${canConfirm && h.rule_id ? `<button type="button" class="btn btn-secondary btn-sm" onclick="updateInquiryPriceMatch('revoke', ${index})">撤销匹配</button>` : ''}</td>
    </tr>`).join('');
    const table = (histories, pending) => histories.length ? `<table class="inquiry-price-review-table"><thead><tr>
        <th>原采购单 / 项目</th><th>供应商 / 含税单价</th><th>原规格参数</th><th>匹配依据 / 操作</th>
        </tr></thead><tbody>${renderRows(histories, pending)}</tbody></table>` : '<p>暂无记录</p>';
    document.getElementById('inquiryPriceReviewBody').innerHTML = `<p><strong>当前材料：</strong>${e(currentText)}</p>
        <p><strong>识别关键参数：</strong>${parameters(row.historical_price_key_parameters)}。工艺、形状及未识别的描述仍保留比较。</p>
        <p><strong>价格口径：</strong>${current.is_cash_price ? '现金含税单价' : '普通含税单价'}；不含运费；仅本单之前审批通过的记录。</p>
        <p><strong>查询结果：</strong>${e(row.historical_price_reason)}${row.historical_lowest_price == null ? '' : '，最低 ' + money(row.historical_lowest_price)}</p>
        <h3>已匹配历史记录</h3>${table(row.historical_price_matches || [], false)}
        <h3>相似规格待确认（未计入最低价）</h3>
        <p>缺少参数不代表参数相同。核对原单后确认；不同地区、单位、明确不同尺寸不可确认。确认规则仅适用于本次参数组合，不修改原单据。</p>
        ${canConfirm ? '<label for="inquiryPriceMatchReason">核对依据（确认前必填）</label><textarea id="inquiryPriceMatchReason" maxlength="500" placeholder="例如：已核对原采购单，确认同为300×3双面焊直角件"></textarea>' : '<p>仅系统管理员、材料审批负责人可确认匹配。</p>'}
        ${table(row.historical_price_candidates || [], true)}`;
}

async function updateInquiryPriceMatch(action, index) {
    const state = inquiryPriceReview;
    if (!state) return;
    const row = state.data;
    const histories = action === 'confirm' ? row.historical_price_candidates : row.historical_price_matches;
    const history = histories[index];
    const reason = document.getElementById('inquiryPriceMatchReason')?.value.trim() || '';
    if (action === 'confirm' && !reason) return showToast('请先填写规格核对依据', 'warning');
    const buttons = document.querySelectorAll('#inquiryPriceReviewBody button');
    buttons.forEach(button => { button.disabled = true; });
    try {
        const response = await api(state.url, { method: 'POST', body: JSON.stringify({
            action, reason, current_key: row.historical_price_current_key, history_key: history.history_key
        }) });
        const result = await response.json();
        if (!response.ok || !result.success) throw new Error(result.message || '更新失败');
        showToast(result.message, 'success');
        // Refresh the visible detail without rebuilding the approval form (which
        // could discard a remark the approver is editing).
        const fresh = await (await api(state.url)).json();
        if (!fresh.success) throw new Error(fresh.message || '刷新失败');
        document.querySelectorAll('.inquiry-price-link').forEach(button => {
            if (button.getAttribute('onclick') === `openInquiryPriceHistory(${state.inquiryId}, ${state.itemId}, ${state.legacy ? 'true' : 'false'})`) {
                button.closest('td').innerHTML = renderInquiryHistoricalPrice(fresh.data);
            }
        });
        inquiryPriceReview = { ...state, ...fresh };
        renderInquiryPriceReview();
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        buttons.forEach(button => { button.disabled = false; });
    }
}
