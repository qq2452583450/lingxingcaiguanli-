/* 供应商报价平台 JS */
(function () {
    'use strict';

    let currentUser = null;
    let currentInquiryId = null;
    let currentQuotes = [];
    let currentFreight = { tax_freight: 0, tax_rate: 0.13, remark: '' };
    let quoteDeadline = null;
    let csrfToken = '';

    // ==================== CSRF ====================
    async function fetchCsrfToken() {
        try {
            const resp = await fetch('/api/csrf-token', { credentials: 'same-origin' });
            const data = await resp.json();
            if (data.success) csrfToken = data.csrf_token;
        } catch (e) { /* ignore */ }
    }

    // ==================== API Helper ====================
    async function api(url, options = {}) {
        const headers = { 'Content-Type': 'application/json' };
        if (csrfToken) headers['X-CSRF-Token'] = csrfToken;
        const defaults = { headers, credentials: 'same-origin' };
        const resp = await fetch(url, { ...defaults, ...options });
        return resp.json();
    }

    function toast(msg, type = 'info') {
        const container = document.getElementById('toastContainer');
        const el = document.createElement('div');
        el.className = 'toast ' + type;
        el.textContent = msg;
        container.appendChild(el);
        setTimeout(() => el.remove(), 3500);
    }

    function showAuthMessage(msg, type = 'error') {
        const el = document.getElementById('authMessage');
        el.textContent = msg;
        el.className = 'auth-message ' + type;
        el.classList.remove('hidden');
    }

    function hideAuthMessage() {
        document.getElementById('authMessage').classList.add('hidden');
    }

    // ==================== Auth ====================
    window.showLogin = function () {
        document.getElementById('loginForm').classList.remove('hidden');
        document.getElementById('registerForm').classList.add('hidden');
        hideAuthMessage();
    };

    window.showRegister = function () {
        document.getElementById('loginForm').classList.add('hidden');
        document.getElementById('registerForm').classList.remove('hidden');
        hideAuthMessage();
    };

    window.doLogin = async function () {
        const username = document.getElementById('loginUsername').value.trim();
        const password = document.getElementById('loginPassword').value.trim();
        if (!username || !password) { showAuthMessage('请填写账号和密码'); return; }

        const res = await api('/api/supplier/login', {
            method: 'POST', body: JSON.stringify({ username, password })
        });
        if (res.success) {
            currentUser = res.user;
            await fetchCsrfToken();
            enterMain();
        } else {
            showAuthMessage(res.message);
        }
    };

    window.doRegister = async function () {
        const supplier_name = document.getElementById('regSupplierName').value.trim();
        const contact = document.getElementById('regContact').value.trim();
        const phone = document.getElementById('regPhone').value.trim();
        const address = document.getElementById('regAddress').value.trim();
        const username = document.getElementById('regUsername').value.trim();
        const password = document.getElementById('regPassword').value.trim();
        const password2 = document.getElementById('regPassword2').value.trim();

        if (!supplier_name) { showAuthMessage('请填写供应商名称'); return; }
        if (!username) { showAuthMessage('请填写登录账号'); return; }
        if (!password || password.length < 6) { showAuthMessage('密码至少6位'); return; }
        if (password !== password2) { showAuthMessage('两次密码不一致'); return; }

        const res = await api('/api/supplier/register', {
            method: 'POST', body: JSON.stringify({ supplier_name, contact, phone, address, username, password })
        });
        if (res.success) {
            showAuthMessage(res.message || '注册成功，请等待审核', 'success');
            setTimeout(() => showLogin(), 2000);
        } else {
            showAuthMessage(res.message);
        }
    };

    window.doLogout = async function () {
        await api('/api/supplier/logout', { method: 'POST' });
        currentUser = null;
        document.getElementById('authPage').classList.remove('hidden');
        document.getElementById('mainPage').classList.add('hidden');
        document.getElementById('loginUsername').value = '';
        document.getElementById('loginPassword').value = '';
        hideAuthMessage();
    };

    // ==================== Main ====================
    function enterMain() {
        document.getElementById('authPage').classList.add('hidden');
        document.getElementById('mainPage').classList.remove('hidden');
        document.getElementById('supplierNameDisplay').textContent = currentUser.supplier_name;

        // 检查资料是否完善
        if (!currentUser.profile_completed) {
            showProfileView();
        } else {
            showQuoteListView();
        }
    }

    function showProfileView() {
        document.getElementById('profileView').classList.remove('hidden');
        document.getElementById('quoteListView').classList.add('hidden');
        document.getElementById('quoteDetailView').classList.add('hidden');
        loadProfile();
    }

    function showQuoteListView() {
        document.getElementById('profileView').classList.add('hidden');
        document.getElementById('quoteListView').classList.remove('hidden');
        document.getElementById('quoteDetailView').classList.add('hidden');
        loadQuoteRequests();
    }

    async function checkSession() {
        await fetchCsrfToken();
        const res = await api('/api/supplier/me');
        if (res.success) {
            currentUser = res.user;
            // 如果有 profile 数据，预填
            if (res.profile) {
                currentUser._profile = res.profile;
            }
            enterMain();
        }
    }

    // ==================== Profile ====================
    async function loadProfile() {
        const res = await api('/api/supplier/me');
        if (!res.success) return;
        const p = res.profile || {};
        document.getElementById('profileSupplierName').value = p.supplier_name || '';
        document.getElementById('profileContact').value = p.contact || '';
        document.getElementById('profilePhone').value = p.phone || '';
        document.getElementById('profileAddress').value = p.address || '';
        document.getElementById('profileBusinessScope').value = p.business_scope || '';
        document.getElementById('profileUsername').value = currentUser.username || '';
    }

    window.submitProfile = async function () {
        const msgEl = document.getElementById('profileMessage');
        msgEl.classList.add('hidden');

        const body = {
            supplier_name: document.getElementById('profileSupplierName').value.trim(),
            contact: document.getElementById('profileContact').value.trim(),
            phone: document.getElementById('profilePhone').value.trim(),
            address: document.getElementById('profileAddress').value.trim(),
            business_scope: document.getElementById('profileBusinessScope').value.trim(),
            password: document.getElementById('profilePassword').value.trim(),
            password2: document.getElementById('profilePassword2').value.trim(),
        };

        const res = await api('/api/supplier/profile', {
            method: 'PUT', body: JSON.stringify(body)
        });

        if (res.success) {
            currentUser.profile_completed = 1;
            currentUser.supplier_name = body.supplier_name;
            document.getElementById('supplierNameDisplay').textContent = body.supplier_name;
            toast('资料已完善', 'success');
            showQuoteListView();
        } else {
            msgEl.textContent = res.message;
            msgEl.className = 'auth-message error';
            msgEl.classList.remove('hidden');
        }
    };

    // ==================== Quote List ====================
    async function loadQuoteRequests() {
        const res = await api('/api/supplier/quote-requests');
        if (!res.success) { toast(res.message, 'error'); return; }

        const list = document.getElementById('quoteList');
        const empty = document.getElementById('quoteListEmpty');

        if (!res.data || res.data.length === 0) {
            list.innerHTML = '';
            empty.classList.remove('hidden');
            return;
        }

        empty.classList.add('hidden');
        list.innerHTML = res.data.map(item => {
            const statusClass = item.inquiry_quote_status || 'pending';
            const statusText = { pending: '待报价', collecting: '报价中', locked: '已锁定' }[statusClass] || statusClass;
            const deadline = item.quote_deadline ? `截止: ${item.quote_deadline}` : '';
            return `
                <div class="quote-card" onclick="openQuoteDetail(${item.inquiry_id})">
                    <div class="quote-card-header">
                        <span class="quote-card-no">${escHtml(item.inquiry_no)}</span>
                        <span class="status-badge ${statusClass}">${statusText}</span>
                    </div>
                    <div class="quote-card-meta">
                        <span>日期: ${escHtml(item.inquiry_date || '-')}</span>
                        ${deadline ? `<span>${deadline}</span>` : ''}
                        ${item.inquiry_remark ? `<span>备注: ${escHtml(item.inquiry_remark)}</span>` : ''}
                    </div>
                </div>
            `;
        }).join('');

        lucide.createIcons();
    }

    // ==================== Quote Detail ====================
    window.openQuoteDetail = async function (inquiryId) {
        currentInquiryId = inquiryId;
        const res = await api(`/api/supplier/quote-requests/${inquiryId}`);
        if (!res.success) { toast(res.message, 'error'); return; }

        document.getElementById('quoteListView').classList.add('hidden');
        document.getElementById('quoteDetailView').classList.remove('hidden');

        const inq = res.inquiry;
        quoteDeadline = inq.quote_deadline;
        document.getElementById('detailInquiryNo').textContent = inq.inquiry_no;

        const statusClass = inq.quote_status || 'collecting';
        const statusText = { draft: '草稿', collecting: '报价中', locked: '已锁定' }[statusClass] || statusClass;
        const badge = document.getElementById('detailQuoteStatus');
        badge.textContent = statusText;
        badge.className = 'status-badge ' + statusClass;

        document.getElementById('inquiryInfo').innerHTML = `
            <span>询价日期: <strong>${escHtml(inq.inquiry_date || '-')}</strong></span>
            ${inq.quote_deadline ? `<span>截止时间: <strong>${escHtml(inq.quote_deadline)}</strong></span>` : ''}
            ${inq.remark ? `<span>备注: <strong>${escHtml(inq.remark)}</strong></span>` : ''}
        `;

        currentQuotes = res.quotes;
        currentFreight = res.freight || { tax_freight: 0, tax_rate: 0.13, remark: '' };
        document.getElementById('quoteFreightTax').value = currentFreight.tax_freight || '';
        document.getElementById('quoteFreightRate').value = currentFreight.tax_rate ?? 0.13;
        document.getElementById('quoteFreightRemark').value = currentFreight.remark || '';
        renderQuoteTable();
    };

    function renderQuoteTable() {
        const tbody = document.getElementById('quoteTableBody');
        const isLocked = currentQuotes.some(q => q.quote_status === 'locked');
        const canEdit = !isLocked;

        tbody.innerHTML = currentQuotes.map((q, i) => {
            const quoteStatus = q.quote_status || 'pending';
            const statusText = { pending: '待报价', saved: '已保存', submitted: '已提交', locked: '已锁定' }[quoteStatus] || quoteStatus;
            const disabled = quoteStatus === 'locked' ? 'disabled' : '';
            const isGb = q.is_national_standard == 1 ? '是' : '否';
            return `
                <tr>
                    <td>${i + 1}</td>
                    <td style="text-align:left;">${escHtml(q.material_name || '-')}</td>
                    <td>${escHtml(q.specification || '-')}</td>
                    <td>${escHtml(q.detail_spec || '-')}</td>
                    <td>${escHtml(q.brand || '-')}</td>
                    <td>${isGb}</td>
                    <td>${escHtml(q.unit_name || '-')}</td>
                    <td>${q.quantity || 1}</td>
                    <td><input type="number" step="0.01" min="0" value="${q.tax_price || ''}"
                        placeholder="填写单价" onchange="updateQuote(${i}, 'tax_price', this.value)"
                        oninput="updateQuote(${i}, 'tax_price', this.value)" ${disabled} /></td>
                    <td><input type="number" step="0.01" min="0" max="1" value="${q.tax_rate || 0.13}"
                        onchange="updateQuote(${i}, 'tax_rate', this.value)" ${disabled} /></td>
                    <td class="text-right">${q.total_amount ? '¥' + Number(q.total_amount).toFixed(2) : '-'}</td>
                    <td><textarea rows="1" placeholder="备注" onchange="updateQuote(${i}, 'supplier_remark', this.value)"
                        ${disabled}>${escHtml(q.supplier_remark || '')}</textarea></td>
                    <td><span class="status-badge ${quoteStatus}">${statusText}</span></td>
                    <td>${quoteStatus === 'locked' ? '<span class="text-muted">已锁定</span>' : ''}</td>
                </tr>
            `;
        }).join('');

        // Actions
        const actions = document.getElementById('quoteActions');
        if (!canEdit) {
            actions.innerHTML = '<span class="text-muted">报价已锁定，无法修改</span>';
            document.querySelectorAll('#quoteFreight input').forEach(input => input.disabled = true);
        } else {
            document.querySelectorAll('#quoteFreight input').forEach(input => input.disabled = false);
            actions.innerHTML = `
                <button class="btn-save" onclick="saveAllQuotes()">保存草稿</button>
                <button class="btn-submit" onclick="submitAllQuotes()">提交报价</button>
            `;
        }
    }

    window.updateQuote = function (index, field, value) {
        if (!currentQuotes[index]) return;
        if (field === 'tax_price' || field === 'tax_rate') {
            currentQuotes[index][field] = parseFloat(value) || 0;
        } else {
            currentQuotes[index][field] = value;
        }
        // Recalculate
        const q = currentQuotes[index];
        const qty = q.quantity || 1;
        q.total_amount = Math.round((q.tax_price || 0) * qty * 100) / 100;
        q.tax_exempt_price = q.tax_rate ? Math.round((q.tax_price || 0) / (1 + q.tax_rate) * 10000) / 10000 : (q.tax_price || 0);
        // Update total display
        const rows = document.querySelectorAll('#quoteTableBody tr');
        if (rows[index]) {
            const totalCell = rows[index].children[7];
            totalCell.textContent = q.total_amount ? '¥' + q.total_amount.toFixed(2) : '-';
        }
    };

    window.saveAllQuotes = async function () {
        let saved = 0;
        for (const q of currentQuotes) {
            if (q.quote_status === 'locked') continue;
            const res = await api(`/api/supplier/quotes/${q.quote_id}`, {
                method: 'PUT',
                body: JSON.stringify({
                    tax_price: q.tax_price,
                    tax_rate: q.tax_rate,
                    supplier_remark: q.supplier_remark || ''
                })
            });
            if (res.success) saved++;
            else toast(res.message, 'error');
        }
        const freightSaved = await saveInquiryFreight();
        if (!freightSaved) return;
        toast(`已保存 ${saved} 条报价`, 'success');
        // Reload detail
        openQuoteDetail(currentInquiryId);
    };

    async function saveInquiryFreight() {
        const taxFreight = parseFloat(document.getElementById('quoteFreightTax').value) || 0;
        const taxRate = parseFloat(document.getElementById('quoteFreightRate').value) || 0;
        const remark = document.getElementById('quoteFreightRemark').value || '';
        const res = await api(`/api/supplier/quote-requests/${currentInquiryId}/freight`, {
            method: 'PUT',
            body: JSON.stringify({ tax_freight: taxFreight, tax_rate: taxRate, remark })
        });
        if (!res.success) toast(res.message, 'error');
        return !!res.success;
    }

    window.submitAllQuotes = async function () {
        // Validate all have price > 0
        const invalid = currentQuotes.filter(q => q.quote_status !== 'locked' && (!q.tax_price || q.tax_price <= 0));
        if (invalid.length > 0) {
            toast('所有材料的含税单价必须大于0才能提交', 'error');
            return;
        }

        if (!confirm('确认提交所有报价？提交后在截止前仍可修改。')) return;

        let submitted = 0;
        for (const q of currentQuotes) {
            if (q.quote_status === 'locked') continue;
            const res = await api(`/api/supplier/quotes/${q.quote_id}/submit`, {
                method: 'POST',
                body: JSON.stringify({
                    tax_price: q.tax_price,
                    tax_rate: q.tax_rate,
                    supplier_remark: q.supplier_remark || ''
                })
            });
            if (res.success) submitted++;
            else toast(res.message, 'error');
        }
        const freightSaved = await saveInquiryFreight();
        if (!freightSaved) return;
        toast(`已提交 ${submitted} 条报价`, 'success');
        openQuoteDetail(currentInquiryId);
    };

    window.backToList = function () {
        document.getElementById('quoteDetailView').classList.add('hidden');
        document.getElementById('quoteListView').classList.remove('hidden');
        loadQuoteRequests();
    };

    // ==================== Helpers ====================
    function escHtml(s) {
        if (s == null) return '';
        const d = document.createElement('div');
        d.textContent = String(s);
        return d.innerHTML;
    }

    // ==================== Init ====================
    document.addEventListener('DOMContentLoaded', function () {
        lucide.createIcons();
        checkSession();

        // Enter key on login
        document.getElementById('loginPassword').addEventListener('keydown', function (e) {
            if (e.key === 'Enter') doLogin();
        });
        document.getElementById('loginUsername').addEventListener('keydown', function (e) {
            if (e.key === 'Enter') document.getElementById('loginPassword').focus();
        });
    });
})();
