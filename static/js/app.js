// 零星材管理系统 - 前端脚本
let currentUser = null;
let currentProjectId = null;
let userProjects = [];
let materials = [];
let allMaterialsCache = []; // 用于下拉选择的全部材料缓存，与列表分页数据分离
let suppliers = [];
let units = [];
let inquiryItems = [];
let editingInquiryId = null; // 编辑模式下的询价单ID
let stockInDetails = [];
let warehouses = [];
let inventoryCache = [];
let baseStockInSourceWarehouseId = null;
let baseStockInEditId = null;
let baseInventoryCache = [];
let baseTransferRecordsCache = [];
let cartItems = [];
let selectedMaterialIds = new Set();
let csrfToken = '';
let pettyCashLoans = [];
let pettyCashUsages = [];
let pettyCashProjects = [];

// ==================== CSRF Token 管理 ====================
async function fetchCsrfToken() {
    try {
        const res = await api('/api/csrf-token');
        const data = await res.json();
        if (data.success) csrfToken = data.csrf_token;
    } catch (e) { /* 非阻塞 */ }
}

function api(url, options = {}) {
    const headers = { ...options.headers };
    if (csrfToken) headers['X-CSRF-Token'] = csrfToken;
    if (!(options.body instanceof FormData)) {
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    }
    return fetch(url, { ...options, headers });
}

// ==================== 材料列表分页/虚拟滚动状态 ====================
const MATERIAL_PAGE_SIZE = 50;
let materialState = {
    keyword: '',
    page: 1,
    total: 0,
    totalPages: 0,
    loading: false,
    allLoaded: false
};

// ==================== Toast 通知系统 ====================
function showToast(message, type = 'info', duration = 3000) {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const icons = {
        success: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        warning: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        info: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    };
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span>${message}`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('toast-out');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', () => {
    // 初始化 Lucide 图标
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    // 获取 CSRF token
    fetchCsrfToken();
    // 从本地存储加载购物车
    loadCartFromStorage();
    updateCartBadge();
    // 绑定材料搜索防抖
    bindMaterialSearch();
    // 初始化材料列表虚拟滚动
    initMaterialVirtualScroll();
    checkLogin();
});

// ==================== 登录相关 ====================

async function login() {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    if (!username || !password) {
        showToast('请输入用户名和密码', 'warning');
        return;
    }

    // 先清空旧状态，防止界面闪烁
    document.getElementById('mainPage').classList.add('hidden');
    document.getElementById('projectSelectPage').classList.add('hidden');
    document.getElementById('loginPage').classList.add('hidden');

    try {
        const res = await api('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username, password})
        });
        const data = await res.json();

        if (data.success) {
            // 清空旧数据
            currentUser = null;
            currentProjectId = null;
            userProjects = [];
            sessionStorage.removeItem('currentUser');
            sessionStorage.removeItem('currentProjectId');

            currentUser = data.user;
            sessionStorage.setItem('currentUser', JSON.stringify(currentUser));

            if (data.must_change_password || currentUser.must_change_password) {
                showForcePasswordChange();
                return;
            }
            await continueAfterLogin();
        } else {
            document.getElementById('loginPage').classList.remove('hidden');
            showToast(data.message, 'error');
        }
    } catch (e) {
        document.getElementById('loginPage').classList.remove('hidden');
        showToast('登录失败: ' + e.message, 'error');
    }
}

function isAllBoundProjectsUser(user = currentUser) {
    const username = String(user?.username || '').toLowerCase();
    const realName = String(user?.real_name || '');
    return username === 'leikefeng' || username === 'tanxiang' || realName === '雷克峰' || realName === '谭香';
}

async function continueAfterLogin() {
    const projRes = await api('/api/projects?mine=1');
    const projData = await projRes.json();
    userProjects = projData.success ? projData.data : [];

    if (isAllBoundProjectsUser()) {
        currentProjectId = null;
        sessionStorage.removeItem('currentProjectId');
        enterMainSystem();
    } else if (currentUser.role_name === '系统管理员' || userProjects.length <= 1) {
        if (userProjects.length === 1) {
            currentProjectId = userProjects[0].id;
            sessionStorage.setItem('currentProjectId', currentProjectId);
        }
        enterMainSystem();
    } else {
        showProjectSelect();
    }
}

function showForcePasswordChange() {
    document.getElementById('loginPage').classList.add('hidden');
    document.getElementById('projectSelectPage').classList.add('hidden');
    document.getElementById('mainPage').classList.add('hidden');
    document.getElementById('forceNewPassword').value = '';
    document.getElementById('forceConfirmPassword').value = '';
    openModal('modal-force-password-change');
}

async function submitForcePasswordChange(event) {
    event.preventDefault();
    const newPassword = document.getElementById('forceNewPassword').value.trim();
    const confirmPassword = document.getElementById('forceConfirmPassword').value.trim();
    if (newPassword.length < 6) {
        showToast('新密码至少6位', 'warning');
        return;
    }
    if (newPassword !== confirmPassword) {
        showToast('两次输入的密码不一致', 'warning');
        return;
    }

    const res = await api('/api/change-password', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ new_password: newPassword })
    });
    const data = await res.json();
    if (!data.success) {
        showToast(data.message || '修改密码失败', 'error');
        return;
    }
    currentUser.must_change_password = false;
    sessionStorage.setItem('currentUser', JSON.stringify(currentUser));
    closeModal('modal-force-password-change');
    showToast('密码已修改', 'success');
    await continueAfterLogin();
}

function showProjectSelect() {
    document.getElementById('loginPage').classList.add('hidden');
    document.getElementById('mainPage').classList.add('hidden');
    document.getElementById('projectSelectPage').classList.remove('hidden');

    const select = document.getElementById('selectProject');
    select.innerHTML = '<option value="">-- 选择项目 --</option>';
    userProjects.forEach(p => {
        select.innerHTML += `<option value="${p.id}">${escapeHtml(p.project_name)}</option>`;
    });
}

async function confirmProject() {
    const select = document.getElementById('selectProject');
    const projectId = select.value;
    if (!projectId) {
        showToast('请选择项目', 'warning');
        return;
    }
    currentProjectId = parseInt(projectId);
    sessionStorage.setItem('currentProjectId', currentProjectId);
    enterMainSystem();
}

async function openSwitchProjectModal() {
    if (userProjects.length <= 1) {
        showToast('您只有一个绑定项目，无需切换', 'info');
        return;
    }

    const currentProj = userProjects.find(p => p.id === currentProjectId);
    document.getElementById('switchProjectCurrent').textContent = currentProj?.project_name || '-';

    const select = document.getElementById('switchProjectSelect');
    select.innerHTML = '';
    userProjects.forEach(p => {
        if (p.id !== currentProjectId) {
            select.innerHTML += `<option value="${p.id}">${escapeHtml(p.project_name)}</option>`;
        }
    });

    openModal('modal-switch-project');
}

function doSwitchProject() {
    const select = document.getElementById('switchProjectSelect');
    const newProjectId = parseInt(select.value);

    if (!newProjectId) {
        showToast('请选择项目', 'warning');
        return;
    }

    const newProj = userProjects.find(p => p.id === newProjectId);
    currentProjectId = newProjectId;
    sessionStorage.setItem('currentProjectId', currentProjectId);
    document.getElementById('selectedProjectName').textContent = newProj?.project_name;

    closeModal('modal-switch-project');
    showToast('已切换到项目: ' + newProj?.project_name);
}

function enterMainSystem() {
    document.getElementById('loginPage').classList.add('hidden');
    document.getElementById('projectSelectPage').classList.add('hidden');
    document.getElementById('mainPage').classList.remove('hidden');

    document.getElementById('userInfo').textContent = `用户: ${currentUser.real_name}`;
    document.getElementById('userRoleDisplay').textContent = currentUser.role_name;

    document.getElementById('currentProjectDisplay').style.display = 'none';
    document.getElementById('switchProjectBtn').style.display = 'none';

    // 显示项目信息和切换按钮
    if (isAllBoundProjectsUser() && !currentProjectId) {
        document.getElementById('selectedProjectName').textContent = `全部绑定项目(${userProjects.length})`;
        document.getElementById('currentProjectDisplay').style.display = 'block';
    }
    if (currentProjectId) {
        const proj = userProjects.find(p => p.id === currentProjectId);
        if (proj) {
            document.getElementById('selectedProjectName').textContent = proj.project_name;
            document.getElementById('currentProjectDisplay').style.display = 'block';
        }
        if (userProjects.length > 1) {
            document.getElementById('switchProjectBtn').style.display = 'block';
        }
    }

    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    clearDictCache();
    applyPermissionControls();
    bindMaterialSearch();
    initMaterialVirtualScroll();
    loadHome();
}

async function logout() {
    await api('/api/logout', {method: 'POST'});
    currentUser = null;
    currentProjectId = null;
    userProjects = [];
    document.getElementById('mainPage').classList.add('hidden');
    document.getElementById('projectSelectPage').classList.add('hidden');
    document.getElementById('loginPage').classList.remove('hidden');
}

async function checkLogin() {
    try {
        const res = await api('/api/current_user');
        const data = await res.json();
        if (data.success) {
            currentUser = data.user;
            sessionStorage.setItem('currentUser', JSON.stringify(currentUser));

            const projRes = await api('/api/projects?mine=1');
            const projData = await projRes.json();
            userProjects = projData.success ? projData.data : [];

            currentProjectId = sessionStorage.getItem('currentProjectId') ? parseInt(sessionStorage.getItem('currentProjectId')) : null;
            if (currentProjectId && !userProjects.find(p => p.id === currentProjectId)) {
                currentProjectId = userProjects.length === 1 ? userProjects[0].id : null;
            }

            if (currentUser.must_change_password) {
                showForcePasswordChange();
            } else if (isAllBoundProjectsUser()) {
                currentProjectId = null;
                sessionStorage.removeItem('currentProjectId');
                enterMainSystem();
            } else if (currentUser.role_name === '系统管理员' || userProjects.length <= 1) {
                if (userProjects.length === 1) {
                    currentProjectId = userProjects[0].id;
                }
                enterMainSystem();
            } else if (!currentProjectId) {
                showProjectSelect();
            } else {
                enterMainSystem();
            }
        } else {
            document.getElementById('loginPage').classList.remove('hidden');
            document.getElementById('mainPage').classList.add('hidden');
            document.getElementById('projectSelectPage').classList.add('hidden');
        }
    } catch (e) {
        document.getElementById('loginPage').classList.remove('hidden');
        document.getElementById('mainPage').classList.add('hidden');
        document.getElementById('projectSelectPage').classList.add('hidden');
    }
}

// ==================== 页面导航 ====================

function showModule(module) {
    document.querySelectorAll('.module').forEach(m => m.classList.add('hidden'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

    document.getElementById(module + 'Module').classList.remove('hidden');
    // 高亮侧边栏对应项（同时标记底部导航）
    const navItem = document.querySelector(`.nav-item[data-module="${module}"]`);
    if (navItem) navItem.classList.add('active');

    switch(module) {
        case 'home': loadHome(); break;
        case 'material': loadMaterials(); break;
        case 'purchase_inquiry': loadInquiries(); break;
        case 'purchase_order': loadOrders(); break;
        case 'stock_in': loadStockIn(); break;
        case 'stock_out': loadStockOut(); break;
        case 'stock_transfer': loadBaseInventory(); break;
        case 'inventory': loadInventory(); break;
        case 'supplier': loadSuppliers(); break;
        case 'project': loadProjects(); break;
        case 'reconciliation': loadReconciliation(); break;
        case 'owner_supplied': loadOwnerSupplied(); break;
        case 'petty_cash': loadPettyCash(); break;
        case 'system': loadUsers(); break;
    }
}

// ==================== 首页 ====================

async function loadHome() {
    try {
        const res = await api('/api/dashboard');
        const data = await res.json();
        if (data.success) {
            document.getElementById('statPending').textContent = data.data.pending;
            document.getElementById('statWarning').textContent = data.data.warning;
            document.getElementById('statTodayIn').textContent = data.data.today_in;
            document.getElementById('statMaterials').textContent = data.data.total_materials;
            document.getElementById('statSuppliers').textContent = data.data.total_suppliers;
        }
    } catch (e) {
        console.error('加载首页数据失败', e);
    }
}

// ==================== 备用金管理 ====================

function pettyCashMoney(value) {
    const num = Number(value || 0);
    return Number.isFinite(num) ? num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00';
}

function pettyCashDate(value) {
    return value ? String(value).slice(0, 10) : '-';
}

function pettyCashFileLink(filename) {
    if (!filename) return '-';
    const url = `/api/petty-cash/files/${encodeURIComponent(filename)}`;
    return `<a href="${url}" target="_blank" rel="noopener">查看</a>`;
}

function pettyCashSelectedProjectId() {
    const el = document.getElementById('pettyCashProjectFilter');
    return el?.value || '';
}

function pettyCashQuery(extra = {}) {
    const params = new URLSearchParams();
    const projectId = pettyCashSelectedProjectId();
    if (projectId) params.set('project_id', projectId);
    Object.entries(extra).forEach(([key, value]) => {
        if (value) params.set(key, value);
    });
    const query = params.toString();
    return query ? `?${query}` : '';
}

async function loadPettyCashProjects() {
    if (pettyCashProjects.length) return;
    const res = await api('/api/projects?mine=1');
    const data = await res.json();
    pettyCashProjects = data.success ? (data.data || []) : [];
    renderPettyCashProjectOptions();
}

function renderPettyCashProjectOptions() {
    const filter = document.getElementById('pettyCashProjectFilter');
    const loanProject = document.getElementById('pettyCashLoanProject');
    if (!filter || !loanProject) return;

    const selected = filter.value || (currentProjectId ? String(currentProjectId) : '');
    const options = pettyCashProjects.map(project => {
        const id = String(project.id);
        const name = escapeHtml(project.project_name || project.name || '');
        return `<option value="${id}" ${id === selected ? 'selected' : ''}>${name}</option>`;
    }).join('');
    filter.innerHTML = `<option value="">全部项目</option>${options}`;
    if (selected) filter.value = selected;
    loanProject.innerHTML = `<option value="">-- 选择项目 --</option>${options}`;
}

async function loadPettyCash() {
    await loadPettyCashProjects();
    await Promise.all([loadPettyCashSummary(), loadPettyCashLoans(), loadPettyCashUsages()]);
}

async function loadPettyCashSummary() {
    try {
        const res = await api(`/api/petty-cash/summary${pettyCashQuery()}`);
        const data = await res.json();
        if (!data.success) return;
        const summary = data.data || {};
        document.getElementById('pettyCashTotalAmount').textContent = pettyCashMoney(summary.total_amount);
        document.getElementById('pettyCashUsedAmount').textContent = pettyCashMoney(summary.used_amount);
        document.getElementById('pettyCashBalanceAmount').textContent = pettyCashMoney(summary.balance_amount);
        document.getElementById('pettyCashUsageCount').textContent = summary.usage_count || 0;
    } catch (e) {
        showToast('备用金汇总加载失败', 'error');
    }
}

async function loadPettyCashLoans() {
    try {
        const res = await api(`/api/petty-cash/loans${pettyCashQuery()}`);
        const data = await res.json();
        if (!data.success) {
            showToast(data.message || '备用金记录加载失败', 'error');
            return;
        }
        pettyCashLoans = data.data || [];
        renderPettyCashLoans();
        renderPettyCashUsageLoanOptions();
    } catch (e) {
        showToast('备用金记录加载失败', 'error');
    }
}

async function loadPettyCashUsages() {
    try {
        const type = document.getElementById('pettyCashTypeFilter')?.value || '';
        const res = await api(`/api/petty-cash/usages${pettyCashQuery({ expense_type: type })}`);
        const data = await res.json();
        if (!data.success) {
            showToast(data.message || '使用情况加载失败', 'error');
            return;
        }
        pettyCashUsages = data.data || [];
        renderPettyCashUsages();
    } catch (e) {
        showToast('使用情况加载失败', 'error');
    }
}

function renderPettyCashLoans() {
    const tbody = document.getElementById('pettyCashLoanTable');
    if (!tbody) return;
    tbody.innerHTML = pettyCashLoans.length ? pettyCashLoans.map(item => `
        <tr>
            <td>${escapeHtml(item.loan_no || '-')}</td>
            <td>${escapeHtml(item.project_name || '-')}</td>
            <td>${pettyCashDate(item.loan_date)}</td>
            <td>${pettyCashMoney(item.total_amount)}</td>
            <td><strong>${pettyCashMoney(item.balance_amount)}</strong></td>
            <td>${pettyCashMoney(item.used_amount)}</td>
            <td>${escapeHtml(item.creator_name || '-')}</td>
            <td>${pettyCashFileLink(item.payment_file_name)}</td>
            <td class="owner-long-text">${escapeHtml(item.remark || '-')}</td>
            <td><button class="btn btn-danger" onclick="deletePettyCashLoan(${item.id})">删除</button></td>
        </tr>
    `).join('') : '<tr><td colspan="10" class="empty-message">暂无备用金记录</td></tr>';
}

function renderPettyCashUsages() {
    const tbody = document.getElementById('pettyCashUsageTable');
    if (!tbody) return;
    tbody.innerHTML = pettyCashUsages.length ? pettyCashUsages.map(item => `
        <tr>
            <td>${escapeHtml(item.usage_no || '-')}</td>
            <td>${escapeHtml(item.loan_no || '-')}</td>
            <td>${escapeHtml(item.project_name || '-')}</td>
            <td>${pettyCashDate(item.use_date)}</td>
            <td>${escapeHtml(item.expense_type || '-')}</td>
            <td>${pettyCashMoney(item.amount)}</td>
            <td>${escapeHtml(item.handler || '-')}</td>
            <td>${pettyCashFileLink(item.proof_file_name)}</td>
            <td class="owner-long-text">${escapeHtml(item.description || '-')}</td>
            <td><button class="btn btn-danger" onclick="deletePettyCashUsage(${item.id})">删除</button></td>
        </tr>
    `).join('') : '<tr><td colspan="10" class="empty-message">暂无使用情况</td></tr>';
}

function renderPettyCashUsageLoanOptions() {
    const select = document.getElementById('pettyCashUsageLoan');
    if (!select) return;
    select.innerHTML = '<option value="">-- 选择备用金单号 --</option>' + pettyCashLoans
        .filter(item => Number(item.balance_amount || 0) > 0)
        .map(item => `<option value="${item.id}">${escapeHtml(item.loan_no || '')} - ${escapeHtml(item.project_name || '')}（余额 ${pettyCashMoney(item.balance_amount)}）</option>`)
        .join('');
}

function openPettyCashLoanModal() {
    renderPettyCashProjectOptions();
    document.getElementById('pettyCashLoanForm').reset();
    document.getElementById('pettyCashLoanDate').value = new Date().toISOString().slice(0, 10);
    const selectedProject = pettyCashSelectedProjectId() || (currentProjectId ? String(currentProjectId) : '');
    if (selectedProject) document.getElementById('pettyCashLoanProject').value = selectedProject;
    openModal('modal-petty-cash-loan');
}

function openPettyCashUsageModal() {
    renderPettyCashUsageLoanOptions();
    document.getElementById('pettyCashUsageForm').reset();
    document.getElementById('pettyCashUsageDate').value = new Date().toISOString().slice(0, 10);
    document.getElementById('pettyCashHandler').value = currentUser?.real_name || '';
    openModal('modal-petty-cash-usage');
}

async function deletePettyCashLoan(id) {
    if (!confirm('确定删除该备用金借款记录吗？已有使用明细的记录不能删除。')) return;
    const res = await api(`/api/petty-cash/loans/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (!data.success) {
        showToast(data.message || '删除失败', 'error');
        return;
    }
    showToast('删除成功', 'success');
    await loadPettyCash();
}

async function deletePettyCashUsage(id) {
    if (!confirm('确定删除该使用情况记录吗？删除后会恢复对应备用金余额。')) return;
    const res = await api(`/api/petty-cash/usages/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (!data.success) {
        showToast(data.message || '删除失败', 'error');
        return;
    }
    showToast('删除成功', 'success');
    await loadPettyCash();
}

document.getElementById('pettyCashLoanForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);
    const res = await api('/api/petty-cash/loans', { method: 'POST', body: formData });
    const data = await res.json();
    if (!data.success) {
        showToast(data.message || '保存失败', 'error');
        return;
    }
    closeModal('modal-petty-cash-loan');
    showToast(`保存成功，单号：${data.loan_no}`, 'success');
    await loadPettyCash();
});

document.getElementById('pettyCashUsageForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);
    const res = await api('/api/petty-cash/usages', { method: 'POST', body: formData });
    const data = await res.json();
    if (!data.success) {
        showToast(data.message || '保存失败', 'error');
        return;
    }
    closeModal('modal-petty-cash-usage');
    showToast(`保存成功，明细单号：${data.usage_no}`, 'success');
    await loadPettyCash();
});

// ==================== 材料管理 ====================

// 辅助函数：安全格式化数字
function safeNum(val, decimals = 2, prefix = '') {
    const num = parseFloat(val);
    if (isNaN(num)) return prefix + '-';
    return prefix + num.toFixed(decimals);
}

function roundMoney(val, decimals = 2) {
    const num = parseFloat(val);
    if (!Number.isFinite(num)) return 0;
    const factor = Math.pow(10, decimals);
    return Math.round((num + Number.EPSILON) * factor) / factor;
}

// 辅助函数：安全格式化税率
function safeRate(val) {
    const num = parseFloat(val);
    if (isNaN(num) || num === 0) return '-';
    return (num * 100).toFixed(0) + '%';
}

// 辅助函数：格式化是否国标
function formatNationalStandard(val) {
    return val == 1 ? '是' : '否';
}

// 辅助函数：编码前缀转区域名
function codeToRegion(code) {
    if (!code) return '-';
    const prefix = (code.substring(0, 2) || '').toUpperCase();
    const map = { 'AN': '安宁', 'KM': '昆明', 'BN': '版纳', 'DL': '大理', 'YX': '玉溪', 'CD': '成都', 'GX': '广西' };
    return map[prefix] || '-';
}

// 权限判断
function isAdmin() {
    const user = JSON.parse(sessionStorage.getItem('currentUser') || '{}');
    return user.role_name === '系统管理员';
}

function isMaterialClerk() {
    const user = JSON.parse(sessionStorage.getItem('currentUser') || '{}');
    return user.role_name === '材料员';
}

function isMaterialApprovalOwner() {
    const user = JSON.parse(sessionStorage.getItem('currentUser') || '{}');
    return user.role_name === '材料审批负责人';
}

function canApprove() {
    return isAdmin() || isMaterialApprovalOwner();
}

function isSpecialApprovalInquiry(inquiry) {
    const projectCode = String(inquiry?.project_code || '').toUpperCase();
    const applicantUsername = String(inquiry?.applicant_username || '').toLowerCase();
    return projectCode.startsWith('GX') || applicantUsername === 'wanglihua';
}

function isSpecialRequiredApprover() {
    const user = JSON.parse(sessionStorage.getItem('currentUser') || '{}');
    return user.username === 'leikefeng' || user.username === 'tanxiang';
}

function canApproveInquiry(inquiry) {
    if (!canApprove()) return false;
    if (!isSpecialApprovalInquiry(inquiry)) return true;
    return isSpecialRequiredApprover();
}

function isInquiryApprovalOpen(status) {
    return status === '待审批' || status === '退回修改' || status === '报价未发布';
}

function canDeleteInquiry(inquiry) {
    return isAdmin() || (isMaterialClerk() && inquiry.approval_status === '草稿');
}

function canCreateSupplier() {
    const user = JSON.parse(sessionStorage.getItem('currentUser') || '{}');
    const username = String(user.username || '').toLowerCase();
    const realName = String(user.real_name || '');
    return isAdmin() || isMaterialClerk() || username === 'tanxiang' || realName === '谭香';
}

function applyPermissionControls() {
    document.querySelectorAll('.admin-only').forEach(el => {
        el.style.display = isAdmin() ? '' : 'none';
    });
    // 管理员和材料员都可以新建材料
    document.querySelectorAll('.material-manager').forEach(el => {
        el.style.display = (isAdmin() || isMaterialClerk()) ? '' : 'none';
    });
    document.querySelectorAll('.approve-only').forEach(el => {
        el.style.display = canApprove() ? '' : 'none';
    });
    // 材料员不能访问项目管理和系统设置
    document.querySelectorAll('.admin-only-nav').forEach(el => {
        el.style.display = isAdmin() ? '' : 'none';
    });
    // 材料员不能删除供应商
    document.querySelectorAll('.supplier-delete-btn').forEach(el => {
        el.style.display = isAdmin() ? '' : 'none';
    });
    document.querySelectorAll('.supplier-create-btn').forEach(el => {
        el.style.display = canCreateSupplier() ? '' : 'none';
    });
}

// 防抖函数
function debounce(fn, delay = 300) {
    let timer = null;
    return function(...args) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

// 初始化材料列表虚拟滚动
function initMaterialVirtualScroll() {
    const container = document.getElementById('materialTableContainer');
    if (!container) return;

    container.addEventListener('scroll', debounce(function() {
        const { scrollTop, scrollHeight, clientHeight } = container;
        // 滚动到底部附近（距离底部100px）时加载更多
        if (scrollHeight - scrollTop - clientHeight < 100 && !materialState.loading && !materialState.allLoaded) {
            loadMoreMaterials();
        }
    }, 200));
}

// 加载材料（首次或搜索）
async function loadMaterials() {
    const nameFilter = document.getElementById('filterName')?.value || '';
    const specFilter = document.getElementById('filterSpec')?.value || '';
    const brandFilter = document.getElementById('filterBrand')?.value || '';
    const regionFilter = document.getElementById('filterRegion')?.value || '';
    materialState.page = 1;
    materialState.allLoaded = false;

    // 保留原有DOM结构和CSS类名，只更新加载状态
    const tbody = document.getElementById('materialTable');
    if (tbody) {
        tbody.innerHTML = '<tr class="loading-row"><td colspan="15"><div class="loading-spinner">加载中...</div></td></tr>';
    }

    const params = new URLSearchParams({page: '1', page_size: String(MATERIAL_PAGE_SIZE)});
    if (nameFilter) params.set('filter_name', nameFilter);
    if (specFilter) params.set('filter_spec', specFilter);
    if (brandFilter) params.set('filter_brand', brandFilter);
    if (regionFilter) params.set('filter_region', regionFilter);

    try {
        const res = await api(`/api/materials?${params.toString()}`, { credentials: 'same-origin' });
        const data = await res.json();
        if (data.success) {
            materials = data.data || [];
            materialState.total = data.total || 0;
            materialState.totalPages = data.total_pages || 1;
            materialState.allLoaded = materials.length >= materialState.total;
            renderMaterialTable();
            updateSelectionUI();
            updateMaterialStats();
        }
    } catch (e) {
        console.error('加载材料失败', e);
        if (tbody) {
            tbody.innerHTML = '<tr class="error-row"><td colspan="15"><div class="error-message">加载失败，请重试</div></td></tr>';
        }
    }
}

let materialFilterData = { names: [], specs: [], brands: [] };
let materialFilterTimer = null;

function onMaterialFilterChange() {
    clearTimeout(materialFilterTimer);
    materialFilterTimer = setTimeout(() => loadMaterials(), 300);
}

function clearMaterialFilters() {
    document.getElementById('filterName').value = '';
    document.getElementById('filterSpec').value = '';
    document.getElementById('filterBrand').value = '';
    document.getElementById('filterRegion').value = '';
    loadMaterials();
}

// 加载更多材料（触底懒加载）
async function loadMoreMaterials() {
    if (materialState.loading || materialState.allLoaded) return;
    materialState.loading = true;

    // 显示加载中状态，保留现有数据行
    const tbody = document.getElementById('materialTable');
    if (tbody) {
        // 移除之前的"加载更多"提示行
        const existingLoadMore = tbody.querySelector('.load-more-row');
        if (existingLoadMore) {
            existingLoadMore.innerHTML = '<td colspan="15"><div class="loading-spinner">加载中...</div></td>';
        }
    }

    const nextPage = materialState.page + 1;
    const params = new URLSearchParams({page: String(nextPage), page_size: String(MATERIAL_PAGE_SIZE)});
    const nameFilter = document.getElementById('filterName')?.value || '';
    const specFilter = document.getElementById('filterSpec')?.value || '';
    const brandFilter = document.getElementById('filterBrand')?.value || '';
    const regionFilter = document.getElementById('filterRegion')?.value || '';
    if (nameFilter) params.set('filter_name', nameFilter);
    if (specFilter) params.set('filter_spec', specFilter);
    if (brandFilter) params.set('filter_brand', brandFilter);
    if (regionFilter) params.set('filter_region', regionFilter);
    try {
        const res = await api(`/api/materials?${params.toString()}`, { credentials: 'same-origin' });
        const data = await res.json();
        if (data.success && data.data) {
            // 追加新数据，不清空现有数据
            materials = materials.concat(data.data || []);
            materialState.page = nextPage;
            materialState.allLoaded = materials.length >= data.total;
            renderMaterialTable();
            updateSelectionUI();
        }
    } catch (e) {
        console.error('加载更多材料失败', e);
        // 恢复"加载更多"提示
        if (tbody) {
            const existingLoadMore = tbody.querySelector('.load-more-row');
            if (existingLoadMore) {
                existingLoadMore.innerHTML = '<td colspan="15"><div class="error-message">加载失败，请滚动重试</div></td>';
            }
        }
    } finally {
        materialState.loading = false;
    }
}

function renderMaterialTable() {
    const tbody = document.getElementById('materialTable');
    if (!tbody) return;

    // 空数据状态 - 引导用户创建第一条材料
    if (materials.length === 0) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="15"><div class="empty-state"><svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:0.3;margin-bottom:12px"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg><p style="font-size:15px;color:var(--text-primary);margin-bottom:6px">还没有材料</p><p style="font-size:13px;color:var(--text-muted);margin-bottom:16px">点击下方按钮添加第一条材料</p><button class="btn btn-primary" style="margin:0" onclick="openMaterialModal()">新建材料</button></div></td></tr>';
        return;
    }

    // 使用文档片段减少DOM操作
    const fragment = document.createDocumentFragment();
    materials.forEach(m => {
        const tr = document.createElement('tr');
        tr.className = 'material-row';
        tr.innerHTML = `
            <td class="col-select"><input type="checkbox" ${selectedMaterialIds.has(m.id) ? 'checked' : ''} onchange="toggleSelect(${m.id}, this.checked)"></td>
            <td class="col-code">${codeToRegion(m.material_code)}</td>
            <td class="col-name">${escapeHtml(m.material_name) || '-'}</td>
            <td class="col-spec">${escapeHtml(m.specification) || '-'}</td>
            <td class="col-unit">${escapeHtml(m.unit_name) || '-'}</td>
            <td class="col-detail-spec">${escapeHtml(m.detail_spec) || '-'}</td>
            <td class="col-brand">${escapeHtml(m.brand) || '-'}</td>
            <td class="col-national-standard">${formatNationalStandard(m.is_national_standard)}</td>
            <td class="col-rate">${safeRate(m.tax_rate)}</td>
            <td class="col-price">¥${safeNum(m.tax_price)}</td>
            <td class="col-no-tax">¥${safeNum(m.tax_exempt_price)}</td>
            <td class="col-no-tax">¥${safeNum(m.cash_price)}</td>
            <td class="col-price">¥${safeNum(m.cash_tax_price)}</td>
            <td class="col-supplier">${escapeHtml(m.supplier_name) || '-'}</td>
            <td class="col-actions">
                ${(isAdmin() || isMaterialClerk()) ? `<button class="btn btn-secondary" onclick="editMaterial(${m.id})">编辑</button>` : ''}
                ${isAdmin() ? `<button class="btn btn-danger" onclick="deleteMaterial(${m.id})">删除</button>` : ''}
                <button class="btn btn-primary" onclick="addToCart(${m.id})">加入询比价</button>
            </td>
        `;
        fragment.appendChild(tr);
    });

    // 如果还有更多数据，添加加载提示行
    if (!materialState.allLoaded) {
        const loadMoreTr = document.createElement('tr');
        loadMoreTr.className = 'load-more-row';
        loadMoreTr.innerHTML = '<td colspan="15"><div class="load-more-message">滚动加载更多...</div></td>';
        fragment.appendChild(loadMoreTr);
    }

    // 清空并重新填充，保留tbody结构
    tbody.innerHTML = '';
    tbody.appendChild(fragment);
}

function updateMaterialStats() {
    const statsEl = document.getElementById('materialStats');
    if (statsEl) {
        statsEl.textContent = `共 ${materialState.total} 条，当前显示 ${materials.length} 条`;
    }
}

// ==================== 材料勾选功能 ====================

function toggleSelect(materialId, checked) {
    if (checked) {
        selectedMaterialIds.add(materialId);
    } else {
        selectedMaterialIds.delete(materialId);
    }
    updateSelectionUI();
}

function toggleSelectAll(checked) {
    if (checked) {
        materials.forEach(m => selectedMaterialIds.add(m.id));
    } else {
        materials.forEach(m => selectedMaterialIds.delete(m.id));
    }
    renderMaterialTable();
    updateSelectionUI();
}

function clearSelection() {
    selectedMaterialIds.clear();
    updateSelectionUI();
    renderMaterialTable();
}

function updateSelectionUI() {
    const btn = document.getElementById('btnGenerateInquiry');
    const badge = document.getElementById('selectionCount');
    const selectAll = document.getElementById('selectAllMaterials');
    const count = selectedMaterialIds.size;

    if (btn) {
        btn.disabled = count === 0;
        btn.textContent = count > 0 ? `生成询价单(${count})` : '生成询价单';
    }
    if (badge) {
        badge.style.display = count > 0 ? 'inline' : 'none';
        badge.textContent = `已选 ${count} 项`;
    }
    // 更新全选框状态
    if (selectAll && materials.length > 0) {
        const pageSelected = materials.filter(m => selectedMaterialIds.has(m.id)).length;
        selectAll.checked = pageSelected === materials.length;
        selectAll.indeterminate = pageSelected > 0 && pageSelected < materials.length;
    }
}

function generateInquiryFromSelection() {
    if (selectedMaterialIds.size === 0) {
        showToast('请先勾选材料', 'info');
        return;
    }

    // 从 allMaterialsCache（全量缓存）或当前页 materials 中收集选中材料
    const lookup = allMaterialsCache.length > 0 ? allMaterialsCache : materials;
    const selected = [];
    const seen = new Set();
    for (const m of lookup) {
        if (selectedMaterialIds.has(m.id) && !seen.has(m.id)) {
            selected.push(m);
            seen.add(m.id);
        }
    }

    if (selected.length === 0) {
        showToast('未找到选中的材料数据，请刷新后重试', 'info');
        return;
    }

    // 构建 items 数组，复用询价弹窗
    const items = selected.map(m => ({
        material_id: m.id,
        material_name: m.material_name,
        material_code: m.material_code,
        specification: m.specification || '',
        detail_spec: m.detail_spec || '',
        brand: m.brand || '',
        unit_name: m.unit_name || '',
        is_national_standard: m.is_national_standard || 0,
        is_cash_price: m.is_cash_price || 0,
        tax_rate: m.tax_rate || 0.01,
        tax_price: m.tax_price || 0,
        tax_exempt_price: m.tax_exempt_price || 0,
        cash_price: m.cash_price || 0,
        cash_tax_price: m.cash_tax_price || 0,
        library_price: m.tax_price || 0,
        quantity: 1,
        quotes: [],
    }));

    openInquiryWithItems(items);
}

// ==================== 采购购物车功能 ====================

// 购物车暂存到localStorage
function saveCartToStorage() {
    try {
        localStorage.setItem('purchase_cart', JSON.stringify(cartItems));
    } catch (e) {
        console.error('保存购物车失败:', e);
    }
}

// 从localStorage加载购物车
function loadCartFromStorage() {
    try {
        const saved = localStorage.getItem('purchase_cart');
        if (saved) {
            cartItems = JSON.parse(saved);
        }
    } catch (e) {
        console.error('加载购物车失败:', e);
        cartItems = [];
    }
}

function addToCart(materialId) {
    const m = (allMaterialsCache.length > 0 ? allMaterialsCache : materials).find(x => x.id == materialId);
    if (!m) return;
    // 检查是否已在购物车
    if (cartItems.some(c => c.material_id === materialId)) {
        showToast('该材料已在询比价列表中', 'info');
        return;
    }
    cartItems.push({
        material_id: m.id,
        material_code: m.material_code,
        material_name: m.material_name,
        specification: m.specification,
        unit_name: m.unit_name,
        library_price: m.tax_price || 0,
        supplier_id: m.default_supplier_id || '',
        this_price: m.tax_price || 0,
        tax_rate: m.tax_rate || 0.13,
        quantity: 1
    });
    saveCartToStorage();
    updateCartBadge();
    showToast('已加入询比价列表', { credentials: 'same-origin' });
}

function updateCartBadge() {
    const badge = document.getElementById('cartBadge');
    if (badge) {
        badge.textContent = cartItems.length;
        badge.style.display = cartItems.length > 0 ? 'flex' : 'none';
    }
}

function openCartDrawer() {
    const drawer = document.getElementById('cartDrawer');
    const overlay = document.getElementById('cartOverlay');
    if (!drawer) return;
    renderCartItems();
    drawer.classList.add('show');
    overlay.classList.add('show');
}

function closeCartDrawer() {
    const drawer = document.getElementById('cartDrawer');
    const overlay = document.getElementById('cartOverlay');
    if (drawer) drawer.classList.remove('show');
    if (overlay) overlay.classList.remove('show');
}

function removeFromCart(index) {
    cartItems.splice(index, 1);
    saveCartToStorage();
    updateCartBadge();
    renderCartItems();
}

function renderCartItems() {
    const tbody = document.getElementById('cartItems');
    if (!tbody) return;
    const validCart = (cartItems || []).filter(c => c != null);
    if (validCart.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;padding:20px;">购物车是空的，请从材料列表添加</td></tr>';
        return;
    }
    tbody.innerHTML = validCart.map((c, i) => `
        <tr>
            <td>${codeToRegion(c?.material_code || c?.['商品编号'] || '')}</td>
            <td>${escapeHtml(c?.material_name || c?.['商品名'] || '未知材料')}</td>
            <td>${escapeHtml(c?.specification || '-')}</td>
            <td>¥${(c?.library_price || c?.['含税价'] || 0).toFixed(2)}</td>
            <td><button class="btn btn-danger" onclick="removeFromCart(${i})">移除</button></td>
        </tr>
    `).join('');
}

// HTML转义防止XSS
function escapeHtml(str) {
    if (str == null) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// 带防抖的搜索
const debouncedSearch = debounce(() => loadMaterials(), 300);

// 搜索事件绑定（在DOMContentLoaded后调用）
function bindMaterialSearch() {
    const searchInput = document.getElementById('materialSearch');
    if (searchInput) {
        searchInput.addEventListener('input', debouncedSearch);
    }
}

async function openMaterialModal(id = null) {
    await loadUnitsAndSuppliers();

    // 获取区域
    let region = '';
    try {
        const res = await api(`/api/next-material-code?project_id=${currentProjectId}`, { credentials: 'same-origin' });
        const data = await res.json();
        region = codeToRegion(data.material_code || '');
    } catch (e) {}

    document.getElementById('materialRegion').value = region;

    // 清空表格并添加3行空行
    const tbody = document.getElementById('materialBatchBody');
    tbody.innerHTML = '';
    delete tbody.dataset.editId;
    for (let i = 0; i < 3; i++) addMaterialRow();

    openModal('modal-material');
}

let materialRowIdx = 0;
function addMaterialRow(data = {}) {
    const tbody = document.getElementById('materialBatchBody');
    const idx = materialRowIdx++;
    const defaultRate = data.tax_rate || 0.01;
    const defaultSupplier = data.default_supplier_id || '';
    const defaultSupplierName = defaultSupplier ? ((suppliers || []).find(s => s.id == defaultSupplier)?.supplier_name || '') : '';
    const defaultNational = data.is_national_standard || 0;
    const isCash = data.is_cash_price || 0;
    const s = 'width:100%;padding:4px 6px;border:1px solid var(--border-light);border-radius:4px;font-size:12px;';
    const tr = document.createElement('tr');
    tr.id = `mat-row-${idx}`;
    tr.style.borderBottom = '1px solid var(--border-light)';
    tr.innerHTML = `
        <td style="padding:6px;text-align:center;color:#999;">${tbody.children.length + 1}</td>
        <td style="padding:3px;"><input type="text" class="mat-name" value="${escapeHtml(data.material_name || '')}" style="${s}"></td>
        <td style="padding:3px;"><input type="text" class="mat-spec" value="${escapeHtml(data.specification || '')}" style="${s}"></td>
        <td style="padding:3px;"><input type="text" class="mat-detail" value="${escapeHtml(data.detail_spec || '')}" style="${s}"></td>
        <td style="padding:3px;"><input type="text" class="mat-unit" value="${escapeHtml(data.unit_name || '')}" style="${s}width:100%;"></td>
        <td style="padding:3px;position:relative;z-index:4;">
            <div class="mat-supplier-combobox">
                <input type="text" class="mat-supplier-input" value="${escapeHtml(defaultSupplierName)}" placeholder="输入搜索供应商..." style="${s}padding-right:22px;" oninput="filterMatSupplier(this)" onfocus="showMatSupplierList(this)" onblur="hideMatSupplierList(this)">
                <input type="hidden" class="mat-supplier-id" value="${defaultSupplier}">
                <span class="mat-supplier-arrow" onmousedown="toggleMatSupplierList(this.previousElementSibling.previousElementSibling)">&#9662;</span>
                <div class="mat-supplier-list">${getMatSupplierOptions(defaultSupplier)}</div>
            </div>
        </td>
        <td style="padding:3px;position:relative;z-index:3;"><select class="mat-tax-rate" style="${s}">${getTaxRateOptions(defaultRate)}</select></td>
        <td style="padding:3px;text-align:center;position:relative;z-index:3;"><select class="mat-national" style="${s}">
            <option value="0" ${defaultNational == 0 ? 'selected' : ''}>否</option>
            <option value="1" ${defaultNational == 1 ? 'selected' : ''}>是</option>
        </select></td>
        <td style="padding:3px;"><input type="number" step="0.01" class="mat-tax-price" value="${data.tax_price || ''}" style="${s}"></td>
        <td style="padding:3px;text-align:center;"><input type="checkbox" class="mat-is-cash" ${isCash ? 'checked' : ''} onchange="toggleCashInput(${idx})"></td>
        <td style="padding:3px;"><input type="number" step="0.01" class="mat-cash-price" value="${data.cash_price || ''}" ${!isCash ? 'disabled' : ''} style="${s}"></td>
        <td style="padding:3px;"><input type="text" class="mat-remark" value="${escapeHtml(data.remark || '')}" style="${s}"></td>
        <td style="padding:6px;text-align:center;"><button type="button" class="btn btn-danger btn-sm" onclick="removeMaterialRow(${idx})" style="padding:2px 6px;font-size:11px;">删除</button></td>
    `;
    tbody.appendChild(tr);
    updateMaterialRowCount();
}

function removeMaterialRow(idx) {
    const tr = document.getElementById(`mat-row-${idx}`, { credentials: 'same-origin' });
    if (tr) tr.remove();
    updateMaterialRowCount();
}

function updateMaterialRowCount() {
    const count = document.getElementById('materialBatchBody').children.length;
    document.getElementById('materialBatchCount').textContent = `共 ${count} 条`;
    Array.from(document.getElementById('materialBatchBody').children).forEach((tr, i) => {
        tr.children[0].textContent = i + 1;
    });
}

function toggleCashInput(idx) {
    const tr = document.getElementById(`mat-row-${idx}`, { credentials: 'same-origin' });
    const checkbox = tr.querySelector('.mat-is-cash');
    const cashInput = tr.querySelector('.mat-cash-price');
    cashInput.disabled = !checkbox.checked;
    if (!checkbox.checked) cashInput.value = '';
}

// 供应商和税率的option HTML缓存
function getSupplierOptions(selectedId) {
    const opts = '<option value="">-</option>' + (suppliers || []).map(s =>
        `<option value="${s.id}" ${s.id == selectedId ? 'selected' : ''}>${escapeHtml(s.supplier_name || '')}</option>`
    ).join('');
    return opts;
}

function getMatSupplierOptions(selectedId) {
    return (suppliers || []).map(s =>
        `<div class="mat-supplier-option${s.id == selectedId ? ' selected' : ''}" data-id="${s.id}" onmousedown="selectMatSupplierOption(this)">${escapeHtml(s.supplier_name || '')}</div>`
    ).join('');
}

function filterMatSupplier(input) {
    const combobox = input.closest('.mat-supplier-combobox');
    const list = combobox.querySelector('.mat-supplier-list');
    const hiddenId = combobox.querySelector('.mat-supplier-id');
    const keyword = input.value.trim().toLowerCase();
    hiddenId.value = '';
    const options = list.querySelectorAll('.mat-supplier-option');
    let hasVisible = false;
    options.forEach(opt => {
        const name = (opt.textContent || '').toLowerCase();
        const match = !keyword || name.includes(keyword);
        opt.style.display = match ? '' : 'none';
        if (match) hasVisible = true;
    });
    list.classList.toggle('show', hasVisible || !keyword);
}

function showMatSupplierList(input) {
    const combobox = input.closest('.mat-supplier-combobox');
    const list = combobox.querySelector('.mat-supplier-list');
    list.querySelectorAll('.mat-supplier-option').forEach(opt => { opt.style.display = ''; });
    list.classList.add('show');
}

function hideMatSupplierList(input) {
    setTimeout(() => {
        const combobox = input.closest('.mat-supplier-combobox');
        const list = combobox.querySelector('.mat-supplier-list');
        list.classList.remove('show');
        const hiddenId = combobox.querySelector('.mat-supplier-id');
        if (!hiddenId.value) {
            const selected = list.querySelector('.mat-supplier-option.selected');
            input.value = selected ? selected.textContent : '';
        }
    }, 200);
}

function selectMatSupplierOption(option) {
    const combobox = option.closest('.mat-supplier-combobox');
    const input = combobox.querySelector('.mat-supplier-input');
    const hiddenId = combobox.querySelector('.mat-supplier-id');
    input.value = option.textContent;
    hiddenId.value = option.dataset.id;
    combobox.querySelectorAll('.mat-supplier-option').forEach(o => o.classList.remove('selected'));
    option.classList.add('selected');
}

function toggleMatSupplierList(input) {
    const combobox = input.closest('.mat-supplier-combobox');
    const list = combobox.querySelector('.mat-supplier-list');
    if (list.classList.contains('show')) {
        list.classList.remove('show');
    } else {
        list.querySelectorAll('.mat-supplier-option').forEach(opt => { opt.style.display = ''; });
        list.classList.add('show');
        input.focus();
    }
}

function getTaxRateOptions(selected) {
    return `<option value="0.01" ${selected == 0.01 ? 'selected' : ''}>1%</option>
            <option value="0.06" ${selected == 0.06 ? 'selected' : ''}>6%</option>
            <option value="0.09" ${selected == 0.09 ? 'selected' : ''}>9%</option>
            <option value="0.13" ${selected == 0.13 ? 'selected' : ''}>13%</option>`;
}

async function saveAllMaterials() {
    const tbody = document.getElementById('materialBatchBody');
    const rows = tbody.children;
    if (rows.length === 0) { showToast('请先添加材料', 'warning'); return; }

    const editId = tbody.dataset.editId;

    function readRow(row) {
        return {
            material_name: row.querySelector('.mat-name').value.trim(),
            specification: row.querySelector('.mat-spec').value.trim(),
            detail_spec: row.querySelector('.mat-detail').value.trim(),
            unit_name: row.querySelector('.mat-unit').value.trim(),
            tax_price: parseFloat(row.querySelector('.mat-tax-price').value) || 0,
            cash_price: parseFloat(row.querySelector('.mat-cash-price').value) || 0,
            is_cash_price: row.querySelector('.mat-is-cash').checked ? 1 : 0,
            is_national_standard: parseInt(row.querySelector('.mat-national').value) || 0,
            tax_rate: parseFloat(row.querySelector('.mat-tax-rate').value) || 0.01,
            default_supplier_id: row.querySelector('.mat-supplier-id').value ? parseInt(row.querySelector('.mat-supplier-id').value) : null,
            remark: row.querySelector('.mat-remark').value.trim()
        };
    }

    if (editId) {
        const body = readRow(rows[0]);
        try {
            const res = await api(`/api/materials/${editId}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body)
            });
            const data = await res.json();
            if (data.success) { showToast('更新成功', 'success'); closeModal('modal-material'); loadMaterials(); }
            else { showToast(data.message, 'error'); }
        } catch (e) { showToast('保存失败: ' + e.message, 'error'); }
        return;
    }

    const items = [];
    for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        const item = readRow(row);
        if (!item.material_name && !item.specification && !item.unit_name) {
            continue;
        }
        if (!item.material_name || !item.specification || !item.unit_name) {
            showToast(`第 ${i + 1} 行：材料名称、规格、单位不能为空`, 'warning');
            return;
        }
        if (!item.detail_spec) {
            showToast(`第 ${i + 1} 行：详细规格不能为空`, 'warning');
            return;
        }
        if (!item.default_supplier_id) {
            showToast(`第 ${i + 1} 行：供应商不能为空`, 'warning');
            return;
        }
        if (item.is_national_standard === '' || item.is_national_standard === null || item.is_national_standard === undefined) {
            showToast(`第 ${i + 1} 行：请选择是否国标`, 'warning');
            return;
        }
        items.push({ ...item, project_id: currentProjectId });
    }
    if (items.length === 0) {
        showToast('请至少填写一行材料信息', 'warning');
        return;
    }

    try {
        const res = await api('/api/materials/batch', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ items, region: document.getElementById('materialRegion').value })
        });
        const data = await res.json();
        if (data.success) {
            showToast(`成功创建 ${data.created || items.length} 个材料`, { credentials: 'same-origin' });
            closeModal('modal-material');
            loadMaterials();
        } else {
            showToast(data.message || '保存失败', 'error');
        }
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

async function editMaterial(id) {
    const m = (allMaterialsCache.length > 0 ? allMaterialsCache : materials).find(x => x.id === id);
    if (!m) return;
    await loadUnitsAndSuppliers();

    document.getElementById('materialRegion').value = codeToRegion(m.material_code || '');

    const tbody = document.getElementById('materialBatchBody');
    tbody.innerHTML = '';
    materialRowIdx = 0;
    addMaterialRow({
        material_name: m.material_name, specification: m.specification,
        detail_spec: m.detail_spec, unit_name: m.unit_name,
        tax_price: m.tax_price, cash_price: m.cash_price, remark: m.remark,
        tax_rate: m.tax_rate, default_supplier_id: m.default_supplier_id,
        is_national_standard: m.is_national_standard, is_cash_price: m.is_cash_price
    });

    tbody.dataset.editId = id;
    openModal('modal-material');
}

async function deleteMaterial(id) {
    if (!confirm('确定要删除该材料吗？')) return;

    try {
        const res = await api(`/api/materials/${id}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            showToast('删除成功', { credentials: 'same-origin' });
            loadMaterials();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

async function deleteInquiry(id) {
    if (!confirm('确定要删除该询价单吗？')) return;

    try {
        const res = await api(`/api/purchase-inquiries/${id}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            showToast('删除成功', { credentials: 'same-origin' });
            loadInquiries();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

async function recallInquiry(id) {
    if (!confirm('确定要撤回此询价单吗？撤回后状态将变为草稿，可重新编辑后提交。')) return;

    try {
        const res = await api(`/api/purchase-inquiries/${id}/recall`, {method: 'POST', credentials: 'same-origin'});
        const data = await res.json();
        if (data.success) {
            showToast('询价单已撤回', 'success');
            loadInquiries();
            // 如果审批弹窗打开中，关闭它
            closeModal('modal-approval');
        } else {
            showToast(data.message || '撤回失败', 'error');
        }
    } catch (e) {
        showToast('撤回失败', 'error');
    }
}


// ==================== 询价单 ====================

let inquiryFilterTimer = null;

function getInquiryFilterParams() {
    const params = new URLSearchParams();
    const keyword = document.getElementById('inquiryFilterKeyword')?.value.trim();
    const applicant = document.getElementById('inquiryFilterApplicant')?.value.trim();
    const status = document.getElementById('inquiryFilterStatus')?.value;
    const startDate = document.getElementById('inquiryFilterStartDate')?.value;
    const endDate = document.getElementById('inquiryFilterEndDate')?.value;
    const isBelow = document.getElementById('inquiryFilterBelow')?.value;

    if (keyword) params.set('keyword', keyword);
    if (applicant) params.set('applicant', applicant);
    if (status) params.set('status', status);
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (isBelow !== undefined && isBelow !== '') params.set('is_below', isBelow);
    return params;
}

function onInquiryFilterChange() {
    clearTimeout(inquiryFilterTimer);
    inquiryFilterTimer = setTimeout(() => loadInquiries(false), 250);
}

function clearInquiryFilters() {
    ['inquiryFilterKeyword', 'inquiryFilterApplicant', 'inquiryFilterStatus',
     'inquiryFilterStartDate', 'inquiryFilterEndDate', 'inquiryFilterBelow']
        .forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
    loadInquiries(false);
}

async function loadInquiries(refreshDrafts = true) {
    try {
        const params = getInquiryFilterParams();
        const query = params.toString();
        const res = await api(`/api/purchase-inquiries${query ? `?${query}` : ''}`);
        const data = await res.json();
        if (data.success) {
            renderInquiryTable(data.data);
        }
    } catch (e) {
        showToast('加载询价单失败', 'error');
    }
    if (refreshDrafts) {
        loadInquiryDrafts();
    }
}

function renderInquiryTable(inquiries) {
    const tbody = document.getElementById('inquiryTable');
    if (!inquiries || inquiries.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="color:var(--txt3);padding:24px;">没有找到匹配的询价单</td></tr>';
        return;
    }
    tbody.innerHTML = inquiries.map(i => `
        <tr>
            <td>${i.inquiry_no}</td>
            <td>${escapeHtml(i.project_display_name || [i.project_city, i.project_code, i.project_name].filter(Boolean).join(' / ') || '-')}</td>
            <td>${i.inquiry_date || '-'}</td>
            <td>${i.applicant_name || '-'}</td>
            <td>¥${(i.total_amount || 0).toFixed(2)}</td>
            <td>${i.is_below_library_price == 1 ? '是' : '否'}</td>
            <td><span class="status ${getStatusClass(i.approval_status)}">${i.approval_status}</span></td>
            <td style="white-space:nowrap;">
                <button class="btn btn-secondary" style="padding:4px 8px;font-size:12px;" onclick="viewInquiry(${i.id})">查看</button>
                ${i.approval_status === '已同意' ? `<button class="btn btn-primary" style="padding:4px 8px;font-size:12px;" onclick="printInquiryApproval(${i.id})">打印签字单</button>` : ''}
                ${i.approval_status === '已同意' ? `<button class="btn btn-success" style="padding:4px 8px;font-size:12px;" onclick="exportSupplierOrders(${i.id})">导出供货单</button>` : ''}
                ${(isInquiryApprovalOpen(i.approval_status) && canApproveInquiry(i)) || (i.approval_status === '已同意' && isAdmin() && !isSpecialApprovalInquiry(i)) ?
                    `<button class="btn btn-warning" style="padding:4px 8px;font-size:12px;" onclick="approveInquiry(${i.id})">${i.approval_status === '已同意' ? '退回' : '审批'}</button>` : ''}
                ${i.approval_status === '待审批' && currentUser && i.applicant_id === currentUser.id ?
                    `<button class="btn btn-info" style="padding:4px 8px;font-size:12px;" onclick="recallInquiry(${i.id})">撤回</button>` : ''}
                ${(i.approval_status === '退回修改' || i.approval_status === '草稿') && currentUser && i.applicant_id === currentUser.id ?
                    `<button class="btn btn-success" style="padding:4px 8px;font-size:12px;" onclick="editInquiry(${i.id})">编辑</button>` : ''}
                ${canDeleteInquiry(i) ?
                    `<button class="btn btn-danger" style="padding:4px 8px;font-size:12px;" onclick="deleteInquiry(${i.id})">删除</button>` : ''}
            </td>
        </tr>
    `).join('');
}

function exportSupplierOrders(id) {
    window.location.href = `/api/purchase-inquiries/${id}/export-supplier-orders`;
}

/**
 * 渲染合并后的明细比价表格
 * 材料名+规格相同的行合并（rowspan），每种材料只显示一次名称/规格/库内价
 * @param {Array} flatDetails - 扁平化的明细行数据
 * @param {Object} options - {showSelected: bool, showLowest: bool}
 * @returns {string} 表格 HTML
 */
function renderMergedDetailTable(flatDetails, options = {}) {
    if (!flatDetails || flatDetails.length === 0) {
        const cols = 10 + (options.showSelected ? 1 : 0);
        return `<table><thead><tr>
            <th>材料</th><th>规格</th><th>详细规格</th><th>单位</th><th>数量</th><th>库内价</th><th>是否现金价</th>
            <th>供应商</th><th>本次报价</th><th>价差</th>
            ${options.showSelected ? '<th>拟定</th>' : ''}
        </tr></thead><tbody>
            <tr><td colspan="${cols}" style="text-align:center;color:#999;">暂无明细</td></tr>
        </tbody></table>`;
    }

    // 按材料名+规格分组
    const groups = [];
    flatDetails.forEach(d => {
        const key = (d.material_name || '-') + '||' + (d.specification || '-') + '||' + (d.detail_spec || '');
        let group = groups.find(g => g.key === key);
        if (!group) {
            group = { key, material_name: d.material_name || '-', specification: d.specification || '-', detail_spec: d.detail_spec || '', unit_name: d.unit_name || '-', library_price: d.library_price || 0, is_cash_price: d.is_cash_price, rows: [] };
            groups.push(group);
        }
        group.rows.push(d);
    });

    let html = `<table><colgroup>
        <col style="width:12%">
        <col style="width:8%">
        <col style="width:14%">
        <col style="width:5%">
        <col style="width:6%">
        <col style="width:8%">
        <col style="width:7%">
        <col style="width:14%">
        <col style="width:10%">
        <col style="width:10%">
        ${options.showSelected ? '<col style="width:6%">' : ''}
    </colgroup><thead><tr>
        <th>材料</th><th>规格</th><th>详细规格</th><th>单位</th><th>数量</th><th>库内价</th><th>是否现金价</th>
        <th>供应商</th><th>本次报价</th><th>价差</th>
        ${options.showSelected ? '<th>拟定</th>' : ''}
    </tr></thead><tbody>`;

    groups.forEach(g => {
        g.rows.forEach((d, i) => {
            const priceDiff = d.price_diff !== undefined ? d.price_diff : (d.quote_price || d.this_price || 0) - (d.library_price || 0);
            const diffColor = priceDiff < 0 ? 'var(--success)' : priceDiff > 0 ? 'var(--danger)' : 'var(--text-secondary)';
            const quotePrice = d.quote_price || d.this_price || 0;
            const quantity = d.quantity || 1;
            const lowestTag = d.is_lowest == 1 ? ' <span class="status approved" style="font-size:10px;padding:1px 5px;vertical-align:middle;">最低</span>' : '';
            const selectedTag = options.showSelected && d.is_selected == 1 ? '<span class="status processing" style="font-size:11px;">✓</span>' : '';

            html += '<tr>';
            if (i === 0) {
                // 第一行：显示合并的材料名/规格/详细规格/单位/数量/库内价
                const rowspan = g.rows.length > 1 ? ` rowspan="${g.rows.length}"` : '';
                html += `<td${rowspan} style="font-weight:500;vertical-align:middle;">${escapeHtml(g.material_name)}</td>`;
                html += `<td${rowspan} style="vertical-align:middle;">${escapeHtml(g.specification)}</td>`;
                html += `<td${rowspan} style="vertical-align:middle;">${escapeHtml(g.detail_spec)}</td>`;
                html += `<td${rowspan} style="vertical-align:middle;">${escapeHtml(g.unit_name)}</td>`;
                html += `<td${rowspan} style="vertical-align:middle;text-align:center;">${quantity}</td>`;
                html += `<td${rowspan} style="vertical-align:middle;">¥${g.library_price.toFixed(2)}</td>`;
                html += `<td${rowspan} style="vertical-align:middle;text-align:center;">${g.is_cash_price === 1 ? '是' : '否'}</td>`;
            }
            html += `<td>${escapeHtml(d.supplier_name || '-')}</td>`;
            html += `<td style="white-space:nowrap;">¥${quotePrice.toFixed(2)}${lowestTag}</td>`;
            html += `<td style="color:${diffColor};font-weight:500;">${priceDiff >= 0 ? '+' : ''}¥${priceDiff.toFixed(2)}</td>`;
            if (options.showSelected) {
                html += `<td>${selectedTag || '-'}</td>`;
            }
            html += '</tr>';
        });
    });

    html += '</tbody></table>';
    return html;
}

function getStatusClass(status) {
    const map = {
        '待审批': 'pending',
        '材料员已审': 'processing',
        '已同意': 'approved',
        '已驳回': 'rejected',
        '退回修改': 'return',
        '草稿': 'draft',
        '报价未发布': 'draft'
    };
    return map[status] || '';
}

async function viewInquiry(id) {
    try {
        const res = await api(`/api/purchase-inquiries/${id}`, { credentials: 'same-origin' });
        const data = await res.json();
        if (data.success) {
            const i = data.data;
            const isLegacy = data.legacy === true;
            let flatDetails = [];

            if (isLegacy) {
                flatDetails = data.details || [];
            } else {
                // 新结构：展开 items + quotes 为扁平行
                const items = data.items || [];
                items.forEach(item => {
                    const quotes = item.quotes || [];
                    if (quotes.length === 0) {
                        flatDetails.push({
                            material_name: item.material_name || '-',
                            specification: item.specification || '-',
                            detail_spec: item.detail_spec || '',
                            unit_name: item.unit_name || '-',
                            quantity: item.quantity || 1,
                            supplier_name: '-',
                            library_price: item.library_price || 0,
                            is_cash_price: item.is_cash_price,
                            this_price: 0,
                            price_diff: 0,
                            is_lowest: 0
                        });
                    } else {
                        quotes.forEach(q => {
                            const priceDiff = (q.tax_price || 0) - (item.library_price || 0);
                            flatDetails.push({
                                material_name: item.material_name || '-',
                                specification: item.specification || '-',
                                detail_spec: item.detail_spec || '',
                                unit_name: item.unit_name || '-',
                                quantity: item.quantity || 1,
                                supplier_name: q.supplier_name || '-',
                                library_price: item.library_price || 0,
                                is_cash_price: item.is_cash_price,
                                this_price: q.tax_price || 0,
                                price_diff: priceDiff,
                                is_lowest: q.is_lowest || 0,
                                is_selected: q.is_selected || 0
                            });
                        });
                    }
                });
            }

            document.getElementById('detailTitle').textContent = `询价单详情 - ${i.inquiry_no}`;
            // 重新计算总金额（仅选定报价，需要乘以数量）
            let calcTotal = 0;
            flatDetails.forEach(d => {
                if (d.is_selected == 1 && d.this_price > 0) {
                    calcTotal += d.this_price * (d.quantity || 1);
                }
            });
            // 如果没有选定的，用最低价计算
            if (calcTotal === 0) {
                flatDetails.forEach(d => {
                    if (d.is_lowest == 1 && d.this_price > 0) {
                        calcTotal += d.this_price * (d.quantity || 1);
                    }
                });
            }
            const displayTotal = calcTotal > 0 ? calcTotal : (i.total_amount || 0);
            document.getElementById('detailContent').innerHTML = `
                <div class="card">
                    <p><strong>单号:</strong> ${i.inquiry_no}</p>
                    <p><strong>日期:</strong> ${i.inquiry_date || '-'}</p>
                    <p><strong>项目:</strong> ${escapeHtml(i.project_display_name || [i.project_city, i.project_code, i.project_name].filter(Boolean).join(' / ') || '-')}</p>
                    <p><strong>申请人:</strong> ${i.applicant_name || '-'}</p>
                    <p><strong>总金额:</strong> ¥${displayTotal.toFixed(2)}</p>
                    <p><strong>状态:</strong> <span class="status ${getStatusClass(i.approval_status)}">${i.approval_status}</span></p>
                    <p><strong>低于库内价:</strong> ${i.is_below_library_price == 1 ? '是' : '否'}</p>
                    <p><strong>备注:</strong> ${i.remark || '-'}</p>
                </div>
                <h4 style="margin:15px 0;">询价明细</h4>
                <div class="table-container">
                    ${renderMergedDetailTable(flatDetails, { showSelected: true })}
                </div>
            `;
            openModal('modal-detail');
        }
    } catch (e) {
        showToast('加载详情失败', 'error');
    }
}

async function editInquiry(id) {
    try {
        const res = await api(`/api/purchase-inquiries/${id}`, { credentials: 'same-origin' });
        const data = await res.json();
        if (!data.success) {
            showToast('加载询价单失败：' + (data.message || '未知错误'), 'error');
            return;
        }

        const inquiry = data.data;
        const items = data.items || [];

        // 设置编辑模式
        editingInquiryId = id;

        // 确保材料和供应商数据已加载
        await Promise.all([loadUnitsAndSuppliers(), loadAllMaterialsForSelect()]);

        // 将 items/quotes 映射到 inquiryItems 表单数据
        inquiryItems = items.map(item => {
            const m = (allMaterialsCache.length > 0 ? allMaterialsCache : materials || []).find(x => x?.id == item.material_id);
            const selectedQuote = (item.quotes || []).find(q => q.is_selected === 1);
            const mappedQuotes = (item.quotes || []).length > 0
                ? item.quotes.map(q => ({
                    supplier_id: q.supplier_id || '',
                    supplier_name: q.supplier_name || '',
                    tax_price: q.tax_price || 0,
                    tax_exempt_price: q.tax_exempt_price || 0,
                    tax_rate: q.tax_rate || 0.01,
                    total_amount: (q.tax_price || 0) * (item.quantity || 1),
                    is_lowest: q.is_lowest || 0,
                    is_selected: q.is_selected || 0
                }))
                : buildDefaultQuotes();

            return {
                material_id: item.material_id || '',
                material_name: item.material_name || (m ? m.material_name : ''),
                material_code: item.material_code || (m ? m.material_code : ''),
                specification: item.specification || (m ? m.specification : ''),
                detail_spec: item.detail_spec || '',
                brand: item.brand || '',
                unit_name: item.unit_name || (m ? m.unit_name : ''),
                quantity: item.quantity || 1,
                library_price: item.library_price || 0,
                tax_price: m ? (m.tax_price || 0) : 0,
                cash_price: m ? (m.cash_price || 0) : 0,
                selected_quote_id: selectedQuote ? selectedQuote.supplier_id : null,
                is_national_standard: item.is_national_standard,
                is_cash_price: item.is_cash_price,
                quotes: mappedQuotes
            };
        });

        // 打开询价单模态框
        const modal = document.getElementById('modal-inquiry');
        modal.dataset.loaded = 'true'; // 跳过默认初始化
        modal.classList.add('show');

        // 更新标题
        modal.querySelector('.modal-header h2').textContent = `编辑询价单 - ${inquiry.inquiry_no}`;

        // 回填表单字段
        document.getElementById('inquiryDate').value = inquiry.inquiry_date || new Date().toISOString().split('T')[0];
        document.getElementById('inquiryRemark').value = inquiry.remark || '';

        // 加载项目并回填
        await loadProjectsToInquirySelect();
        if (inquiry.project_id) {
            document.getElementById('inquiryProject').value = inquiry.project_id;
        }

        // 渲染明细
        renderInquiryItems();
        updateInquiryTotal();
    } catch (e) {
        console.error('编辑询价单失败:', e);
        showToast('加载询价单失败: ' + e.message, 'error');
    }
}

async function approveInquiry(id) {
    // 打开审批模态框，加载询价单详情和审批历史
    try {
        const [detailRes, historyRes] = await Promise.all([
            api(`/api/purchase-inquiries/${id}`),
            api(`/api/purchase-inquiries/${id}/approval-history`)
        ]);
        const detailData = await detailRes.json();
        const historyData = await historyRes.json();

        if (!detailData.success) {
            showToast('加载询价单失败：' + (detailData.message || '未知错误'), 'error');
            return;
        }

        const inquiry = detailData.data;
        const history = historyData.success ? historyData.data : [];

        // 兼容新旧数据结构：新结构 items+quotes 嵌套，旧结构 details 扁平
        const isLegacy = detailData.legacy === true;
        let flatDetails = [];

        if (isLegacy) {
            flatDetails = detailData.details || [];
        } else {
            // 新结构：展开 items + quotes 为扁平行
            const items = detailData.items || [];
            items.forEach(item => {
                const quotes = item.quotes || [];
                if (quotes.length === 0) {
                    flatDetails.push({
                        material_name: item.material_name || '-',
                        specification: item.specification || '-',
                        detail_spec: item.detail_spec || '',
                        unit_name: item.unit_name || '-',
                        quantity: item.quantity || 1,
                        supplier_name: '-',
                        library_price: item.library_price || 0,
                        is_cash_price: item.is_cash_price,
                        quote_price: 0,
                        is_lowest: 0,
                        is_selected: 0
                    });
                } else {
                    quotes.forEach(q => {
                        const priceDiff = (q.tax_price || 0) - (item.library_price || 0);
                        flatDetails.push({
                            material_name: item.material_name || '-',
                            specification: item.specification || '-',
                            detail_spec: item.detail_spec || '',
                            unit_name: item.unit_name || '-',
                            quantity: item.quantity || 1,
                            supplier_name: q.supplier_name || '-',
                            library_price: item.library_price || 0,
                            is_cash_price: item.is_cash_price,
                            quote_price: q.tax_price || 0,
                            tax_exempt_price: q.tax_exempt_price || 0,
                            price_diff: priceDiff,
                            is_lowest: q.is_lowest || 0,
                            is_selected: q.is_selected || 0
                        });
                    });
                }
            });
        }

        // 填充基本信息
        document.getElementById('approvalInquiryNo').textContent = inquiry.inquiry_no;
        document.getElementById('approvalInquiryDate').textContent = inquiry.inquiry_date || '-';
        document.getElementById('approvalApplicant').textContent = inquiry.applicant_name || '-';
        // 重新计算总金额（仅选定报价，需要乘以数量）
        let approveCalcTotal = 0;
        flatDetails.forEach(d => {
            if (d.is_selected == 1 && d.quote_price > 0) {
                approveCalcTotal += d.quote_price * (d.quantity || 1);
            }
        });
        if (approveCalcTotal === 0) {
            flatDetails.forEach(d => {
                if (d.is_lowest == 1 && d.quote_price > 0) {
                    approveCalcTotal += d.quote_price * (d.quantity || 1);
                }
            });
        }
        const approveDisplayTotal = approveCalcTotal > 0 ? approveCalcTotal : (inquiry.total_amount || 0);
        document.getElementById('approvalTotalAmount').textContent = '¥' + approveDisplayTotal.toFixed(2);
        document.getElementById('approvalBelowLib').textContent = inquiry.is_below_library_price == 1 ? '是' : '否';

        // 状态标签
        const statusEl = document.getElementById('approvalStatus');
        statusEl.innerHTML = `<span class="status ${getStatusClass(inquiry.approval_status)}">${inquiry.approval_status}</span>`;

        // 填充明细表格（比价展示：每种材料下展开各供应商报价，材料名+规格相同行合并）
        const detailWrap = document.getElementById('approvalDetailTableWrap');
        detailWrap.innerHTML = renderMergedDetailTable(flatDetails, { showSelected: true });

        // 根据当前状态生成审批操作按钮（简化：材料员发起，只需主管审批）
        const actionBtns = document.getElementById('approvalActionBtns');
        const actionSection = document.getElementById('approvalActionSection');
        const errorEl = document.getElementById('approvalError');
        errorEl.style.display = 'none';
        document.getElementById('approvalRemark').value = '';
        document.getElementById('approvalRemark').classList.remove('reject-required');

        if (isInquiryApprovalOpen(inquiry.approval_status) || inquiry.approval_status === '已同意') {
            actionSection.style.display = '';
            const isAdmin = currentUser && currentUser.role_name === '系统管理员';
            const isSpecialApproval = isSpecialApprovalInquiry(inquiry);
            const isApproved = inquiry.approval_status === '已同意';
            const isApplicant = currentUser && inquiry.applicant_id === currentUser.id;
            // 已同意状态下，仅管理员可退回
            if (isSpecialApproval && !isSpecialRequiredApprover()) {
                actionSection.style.display = 'none';
                errorEl.textContent = 'GX项目或王利华提交的询价单必须由雷克峰和谭香审批，admin不可审批';
                errorEl.style.display = 'block';
            } else if (isApproved && isAdmin) {
                actionBtns.innerHTML = `
                    <button class="approval-action-btn btn-return" onclick="submitApproval(${id}, 'return')">
                        <span class="action-icon">↩</span>
                        <span class="action-label">
                            <span class="main">退回</span>
                            <span class="sub">退回给申请人修改</span>
                        </span>
                    </button>
                `;
            } else if (inquiry.approval_status === '待审批' && isApplicant && !isAdmin) {
                // 申请人在待审批状态下可撤回
                actionBtns.innerHTML = `
                    <button class="approval-action-btn btn-recall" onclick="recallInquiry(${id})">
                        <span class="action-icon">⟲</span>
                        <span class="action-label">
                            <span class="main">撤回</span>
                            <span class="sub">撤回此询价单，可重新编辑后提交</span>
                        </span>
                    </button>
                `;
            } else if (!isApproved) {
                actionBtns.innerHTML = `
                    <button class="approval-action-btn btn-approve" onclick="submitApproval(${id}, 'manager')">
                        <span class="action-icon">✓</span>
                        <span class="action-label">
                            <span class="main">主管审批通过</span>
                            <span class="sub">同意后将更新库内价格</span>
                        </span>
                    </button>
                    <button class="approval-action-btn btn-reject" onclick="submitApproval(${id}, 'reject')">
                        <span class="action-icon">✕</span>
                        <span class="action-label">
                            <span class="main">驳回</span>
                            <span class="sub">退回此询价单</span>
                        </span>
                    </button>
                    ${isAdmin ? `
                    <button class="approval-action-btn btn-return" onclick="submitApproval(${id}, 'return')">
                        <span class="action-icon">↩</span>
                        <span class="action-label">
                            <span class="main">退回</span>
                            <span class="sub">退回给申请人修改</span>
                        </span>
                    </button>
                    ` : ''}
                `;
            } else {
                actionSection.style.display = 'none';
            }
        } else {
            actionSection.style.display = 'none';
        }

        // 填充审批历史时间线
        const timeline = document.getElementById('approvalTimeline');
        
        // 构建历史记录列表，确保开头有"提交审批"
        let allRecords = [...(history || [])];
        const hasSubmitRecord = allRecords.some(r => r.result === '提交审批');
        if (!hasSubmitRecord) {
            // 兼容旧数据：如果没有"提交审批"记录，在开头插入虚拟记录
            allRecords.unshift({
                result: '提交审批',
                approver_name: inquiry.applicant_name || '-',
                approver_real_name: inquiry.applicant_name || '-',
                remark: '',
                approval_time: inquiry.create_time || inquiry.inquiry_date || '-'
            });
        }
        
        if (allRecords.length === 0) {
            timeline.innerHTML = '<div class="approval-timeline-empty">暂无审批记录</div>';
        } else {
            timeline.innerHTML = allRecords.map(r => {
                let resultClass = 'pending';
                let resultText = r.result || '-';
                if (resultText === '提交审批') resultClass = 'submit';
                else if (resultText.includes('同意') || resultText.includes('通过')) resultClass = 'approved';
                else if (resultText.includes('驳回') || resultText.includes('拒绝')) resultClass = 'rejected';
                else if (resultText === '撤回') resultClass = 'recalled';

                return `
                    <div class="approval-timeline-item ${resultClass}">
                        <div class="timeline-header">
                            <span class="timeline-result ${resultClass}">${resultText}</span>
                            <span class="timeline-approver">${r.approver_name || r.approver_real_name || '-'}</span>
                            <span class="timeline-time">${r.approval_time || '-'}</span>
                        </div>
                        ${r.remark ? `<div class="timeline-remark">意见：${escapeHtml(r.remark)}</div>` : ''}
                    </div>
                `;
            }).join('');
        }

        // 保存当前审批的 inquiry ID
        window._currentApprovalId = id;
        openModal('modal-approval');
    } catch (e) {
        showToast('加载审批信息失败：' + e.message, 'error');
    }
}

async function submitApproval(id, action) {
    const remark = document.getElementById('approvalRemark').value.trim();
    const errorEl = document.getElementById('approvalError');

    // 驳回时必须填写原因
    if (action === 'reject' && !remark) {
        errorEl.textContent = '驳回时必须填写审批意见';
        errorEl.style.display = 'block';
        document.getElementById('approvalRemark').classList.add('reject-required');
        document.getElementById('approvalRemark').focus();
        return;
    }

    errorEl.style.display = 'none';

    // 确认操作
    const actionLabel = action === 'manager' ? '主管审批通过' : action === 'return' ? '退回' : '驳回';
    if (!confirm(`确认执行「${actionLabel}」操作？`)) return;

    // 禁用按钮防止重复提交
    const btns = document.querySelectorAll('.approval-action-btn');
    btns.forEach(btn => btn.classList.add('loading'));

    try {
        const res = await api(`/api/purchase-inquiries/${id}/approve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action, remark})
        });
        const data = await res.json();
        if (data.success) {
            if (action === 'return') {
                // 退回后刷新审批页面，不关闭弹窗
                approveInquiry(id);
                loadInquiries();
            } else {
                closeModal('modal-approval');
                loadInquiries();
                // 如果在首页也刷新统计数据
                if (typeof loadDashboard === 'function') loadDashboard();
            }
        } else {
            errorEl.textContent = data.message || '审批失败';
            errorEl.style.display = 'block';
        }
    } catch (e) {
        errorEl.textContent = '网络错误，请重试';
        errorEl.style.display = 'block';
    } finally {
        btns.forEach(btn => btn.classList.remove('loading'));
    }
}

async function printInquiryApproval(id) {
    window.open(`/api/purchase-inquiries/${id}/approval-print`, '_blank');
}

// ==================== 入库管理 ====================

async function loadStockIn() {
    try {
        const res = await api('/api/stock-in');
        const data = await res.json();
        if (data.success) {
            renderStockInTable(data.data);
            applyPermissionControls();
        }
    } catch (e) {
        showToast('加载入库单失败', 'error');
    }
}

function renderStockInTable(stockIn) {
    const tbody = document.getElementById('stockInTable');
    if (!stockIn || stockIn.length === 0) {
        tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;color:#999;">暂无入库记录</td></tr>';
        return;
    }
    tbody.innerHTML = stockIn.map((s, i) => {
        const nameStr = escapeHtml(s.material_name || '-') + (s.specification ? ' <span style="color:#999;font-size:12px;">(' + escapeHtml(s.specification) + ')</span>' : '');
        const currentStock = s.current_stock !== undefined ? s.current_stock : null;
        const inQty = s.quantity || 0;

        // 库存状态判断
        let stockBadge = '';
        let rowStyle = '';
        let outBtnHtml = '';

        if (currentStock === null || currentStock === undefined) {
            stockBadge = '<span style="color:#999;">-</span>';
            outBtnHtml = `<button class="btn btn-warning" style="padding:4px 12px;font-size:12px;" onclick="openStockOutModal(${s.material_id}, '${escapeHtml(s.material_name || '')}', '${escapeHtml(s.specification || '')}', ${s.unit_price || 0}, ${s.warehouse_id || 1})">出库</button>`;
        } else if (currentStock <= 0) {
            stockBadge = '<span style="color:#e74c3c;font-weight:600;">0 <span style="font-weight:400;font-size:11px;">(已出完)</span></span>';
            rowStyle = 'style="background:#fff5f5;"';
            outBtnHtml = '<button class="btn" style="padding:4px 12px;font-size:12px;background:#ddd;color:#999;cursor:not-allowed;" disabled>已出完</button>';
        } else if (currentStock < inQty) {
            stockBadge = `<span style="color:#f39c12;font-weight:600;">${currentStock} <span style="font-weight:400;font-size:11px;">(部分出库)</span></span>`;
            rowStyle = 'style="background:#fffcf0;"';
            outBtnHtml = `<button class="btn btn-warning" style="padding:4px 12px;font-size:12px;" onclick="openStockOutModal(${s.material_id}, '${escapeHtml(s.material_name || '')}', '${escapeHtml(s.specification || '')}', ${s.unit_price || 0}, ${s.warehouse_id || 1})">出库</button>`;
        } else {
            stockBadge = `<span style="color:#27ae60;font-weight:600;">${currentStock}</span>`;
            outBtnHtml = `<button class="btn btn-warning" style="padding:4px 12px;font-size:12px;" onclick="openStockOutModal(${s.material_id}, '${escapeHtml(s.material_name || '')}', '${escapeHtml(s.specification || '')}', ${s.unit_price || 0}, ${s.warehouse_id || 1})">出库</button>`;
        }

        // 关联询价单
        const relatedInquiry = s.related_order_no && s.source_type === '采购入库'
            ? `<a href="#" onclick="showModule('purchase_inquiry');return false;" title="${escapeHtml(s.related_order_no)}" style="font-size:12px;">${escapeHtml(s.related_order_no)}</a>`
            : '<span style="color:#999;">-</span>';

        return `<tr ${rowStyle}>
            <td>${i + 1}</td>
            <td>${nameStr}</td>
            <td>${inQty} ${escapeHtml(s.unit_name || '')}</td>
            <td>${escapeHtml(s.supplier_name || '-')}</td>
            <td>¥${(s.unit_price || 0).toFixed(2)}</td>
            <td>${stockBadge}</td>
            <td>${escapeHtml(s.warehouse_name || '-')}</td>
            <td>${escapeHtml(s.project_name || '-')}</td>
            <td>${relatedInquiry}</td>
            <td>${s.in_time || '-'}</td>
            <td style="white-space:nowrap;">
                ${outBtnHtml}
                <button class="btn btn-danger admin-only" style="padding:4px 12px;font-size:12px;" onclick="deleteStockIn(${s.id})">删除</button>
            </td>
        </tr>`;
    }).join('');
}

async function deleteStockIn(id) {
    if (!confirm('确定要删除该入库记录吗？')) return;
    try {
        const res = await api(`/api/stock-in/${id}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            showToast('删除成功', { credentials: 'same-origin' });
            loadStockIn();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

async function deleteStockOut(id) {
    if (!confirm('确定要删除该出库记录吗？')) return;
    try {
        const res = await api(`/api/stock-out/${id}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            showToast('删除成功', { credentials: 'same-origin' });
            loadStockOut();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

async function deleteInventory(materialId, warehouseId) {
    if (!confirm('确定要删除该库存记录吗？')) return;
    try {
        const res = await api(`/api/inventory/${materialId}?warehouse_id=${warehouseId}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            showToast('删除成功', { credentials: 'same-origin' });
            loadInventory();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

// ==================== 出库操作 ====================

let currentStockOutItem = null;

// 查看材料的出库历史记录
async function viewStockOutRecords(materialId, materialName) {
    try {
        const res = await api(`/api/stock-out/by-material/${materialId}`, { credentials: 'same-origin' });
        const data = await res.json();
        if (!data.success) {
            showToast('加载出库记录失败', 'error');
            return;
        }
        const records = data.data || [];
        document.getElementById('stockOutRecordsTitle').textContent = `${materialName} - 出库记录`;

        const tbody = document.getElementById('stockOutRecordsTable');
        if (records.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#999;">暂无出库记录</td></tr>';
        } else {
            tbody.innerHTML = records.map((r, i) => `
                <tr>
                    <td>${i + 1}</td>
                    <td>${escapeHtml(r.order_no || '-')}</td>
                    <td>${r.quantity || 0}</td>
                    <td>${escapeHtml(r.warehouse_name || '-')}</td>
                    <td>${r.out_time || '-'}</td>
                    <td>${escapeHtml(r.team_name || '-')}</td>
                    <td>${escapeHtml(r.receiver_name || '-')}</td>
                    <td>${escapeHtml(r.operator_name || '-')}</td>
                </tr>
            `).join('');
        }
        openModal('modal-stock-out-records');
    } catch (e) {
        showToast('加载出库记录失败', 'error');
    }
}

async function openStockOutModal(materialId, materialName, spec, unitPrice, warehouseId = 1) {
    // 从库存API查实时库存
    let stockQty = 0;
    try {
        await loadWarehouses();
        const res = await api('/api/inventory');
        const data = await res.json();
        const inv = (data.data || []).find(i => i.material_id == materialId && i.warehouse_id == warehouseId);
        if (inv) {
            stockQty = inv.quantity || 0;
        }
    } catch (e) {
        console.error('查询库存失败:', e);
    }

    if (stockQty <= 0) {
        showToast('该材料库存为0，无法出库', 'warning');
        return;
    }

    currentStockOutItem = {
        materialId: materialId,
        materialName: materialName,
        specification: spec,
        stockQty: stockQty,
        unitPrice: unitPrice,
        warehouseId: warehouseId
    };

    document.getElementById('stockOutMaterialName').value = materialName;
    document.getElementById('stockOutSpec').value = spec || '-';
    document.getElementById('stockOutStockQty').value = stockQty;
    document.getElementById('stockOutWarehouse').value = warehouses.find(w => w.id == warehouseId)?.warehouse_name || '-';
    document.getElementById('stockOutPrice').value = '¥' + (unitPrice || 0).toFixed(2);
    document.getElementById('stockOutQuantity').value = '';
    document.getElementById('stockOutQuantity').max = stockQty;
    document.getElementById('stockOutTeam').value = '';
    document.getElementById('stockOutReceiver').value = '';
    document.getElementById('stockOutRemark').value = '';

    openModal('modal-stock-out');
}

async function submitStockOut(e) {
    e.preventDefault();
    if (!currentStockOutItem) return;

    const quantity = parseFloat(document.getElementById('stockOutQuantity').value);
    const teamName = document.getElementById('stockOutTeam').value.trim();
    const receiverName = document.getElementById('stockOutReceiver').value.trim();
    const remark = document.getElementById('stockOutRemark').value.trim();

    if (!quantity || quantity <= 0) {
        showToast('请输入有效的出库数量', 'warning');
        return;
    }
    if (quantity > currentStockOutItem.stockQty) {
        showToast('出库数量不能大于库存数量(' + currentStockOutItem.stockQty + ')', 'warning');
        return;
    }
    if (!teamName && !receiverName) {
        showToast('请填写领用班组或领用人', 'warning');
        return;
    }

    try {
        const res = await api('/api/stock-out', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                details: [{
                    material_id: currentStockOutItem.materialId,
                    quantity: quantity,
                    unit_price: currentStockOutItem.unitPrice
                }],
                team_name: teamName,
                receiver_name: receiverName,
                warehouse_id: currentStockOutItem.warehouseId,
                remark: remark
            })
        });
        const data = await res.json();
        if (data.success) {
            showToast('出库成功！单号: ' + data.order_no, { credentials: 'same-origin' });
            closeModal('modal-stock-out');
            currentStockOutItem = null;
            loadStockIn();
        } else {
            showToast('出库失败: ' + data.message, 'error');
        }
    } catch (err) {
        showToast('出库请求失败', 'error');
    }
}

// ==================== 出库管理 ====================

async function loadStockOut() {
    try {
        const res = await api('/api/stock-out');
        const data = await res.json();
        if (data.success) {
            renderStockOutTable(data.data);
            applyPermissionControls();
        }
    } catch (e) {
        showToast('加载出库单失败', 'error');
    }
}

function renderStockOutTable(stockOut) {
    const tbody = document.getElementById('stockOutTable');
    if (!stockOut || stockOut.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:#999;">暂无出库记录</td></tr>';
        return;
    }
    tbody.innerHTML = stockOut.map((s, i) => `
        <tr>
            <td>${i + 1}</td>
            <td>${escapeHtml(s.material_name || '-')}</td>
            <td>${escapeHtml(s.specification || '-')}</td>
            <td>${s.quantity || 0} ${escapeHtml(s.unit_name || '')}</td>
            <td>${escapeHtml(s.warehouse_name || '-')}</td>
            <td>${s.out_time || '-'}</td>
            <td>${escapeHtml(s.team_name || '-')}</td>
            <td>${escapeHtml(s.receiver_name || '-')}</td>
            <td>${escapeHtml(s.operator_name || '-')}</td>
            <td class="admin-only"><button class="btn btn-danger" style="padding:4px 12px;font-size:12px;" onclick="deleteStockOut(${s.id})">删除</button></td>
        </tr>
    `).join('');
}

// ==================== 库存管理 ====================

async function loadInventory() {
    try {
        const res = await api('/api/inventory');
        const data = await res.json();
        if (data.success) {
            inventoryCache = data.data || [];
            renderInventoryTable(data.data);
            applyPermissionControls();
        }
    } catch (e) {
        showToast('加载库存失败', 'error');
    }
}

function renderInventoryTable(inventory) {
    const tbody = document.getElementById('inventoryTable');
    tbody.innerHTML = (inventory || []).map((i, idx) => `
        <tr>
            <td>${idx + 1}</td>
            <td style="font-size:12px;color:var(--txt2);">${escapeHtml(i.material_code || '-')}</td>
            <td>${escapeHtml(i.material_name || '-')}</td>
            <td>${escapeHtml(i.specification || '-')}</td>
            <td style="font-size:12px;color:var(--txt2);">${escapeHtml(i.detail_spec || '-')}</td>
            <td>${escapeHtml(i.unit_name || '-')}</td>
            <td>${escapeHtml(i.project_name || i.warehouse_name || '-')}</td>
            <td>${escapeHtml(i.project_name || '-')}</td>
            <td style="font-weight:600;">${i.quantity || 0}</td>
            <td>¥${(i.unit_price || 0).toFixed(2)}</td>
            <td>¥${((i.quantity || 0) * (i.unit_price || 0)).toFixed(2)}</td>
            <td>
                <button class="btn btn-success" style="padding:4px 8px;font-size:12px;" onclick="openBaseStockInModal(${i.material_id}, ${i.quantity || 0}, ${i.unit_price || 0}, ${i.warehouse_id})">入库基地</button>
                <button class="btn btn-danger admin-only" style="padding:4px 8px;font-size:12px;" onclick="deleteInventory(${i.material_id}, ${i.warehouse_id})">删除</button>
            </td>
        </tr>
    `).join('') || '<tr><td colspan="12" class="loading">暂无数据</td></tr>';
}

// ==================== 材料基地库存 ====================

async function loadWarehouses(force = false) {
    if (!force && warehouses.length > 0) return warehouses;
    try {
        const res = await api('/api/warehouses');
        const data = await res.json();
        if (!data.success) return [];
        warehouses = data.data || [];
        return warehouses;
    } catch (e) {
        showToast('加载存放点失败', 'error');
        return [];
    }
}

let selectedBaseInventoryIds = new Set();

async function loadBaseInventory() {
    try {
        const [inventoryRes, transferRes] = await Promise.all([
            api('/api/base-inventory'),
            api('/api/base-transfers')
        ]);
        const [inventoryData, transferData] = await Promise.all([
            inventoryRes.json(),
            transferRes.json()
        ]);
        if (inventoryData.success) {
            baseInventoryCache = inventoryData.data || [];
            selectedBaseInventoryIds.clear();
            renderBaseInventoryTable(baseInventoryCache);
        }
        if (transferData.success) {
            baseTransferRecordsCache = transferData.data || [];
            renderBaseTransferRecords(baseTransferRecordsCache);
        }
    } catch (e) {
        console.error('loadBaseInventory failed', e);
        showToast('加载基地库存失败', 'error');
    }
}

function toggleBaseInventorySelect(id) {
    if (selectedBaseInventoryIds.has(id)) {
        selectedBaseInventoryIds.delete(id);
    } else {
        selectedBaseInventoryIds.add(id);
    }
}

function toggleSelectAllBaseInventory() {
    const selectAll = document.getElementById('selectAllBaseInventory');
    if (selectAll.checked) {
        baseInventoryCache.forEach(item => selectedBaseInventoryIds.add(item.id));
    } else {
        selectedBaseInventoryIds.clear();
    }
    renderBaseInventoryTable(baseInventoryCache);
}

function renderBaseInventoryTable(records) {
    const tbody = document.getElementById('baseInventoryTable');
    const selectAll = document.getElementById('selectAllBaseInventory');
    const allSelected = (records || []).length > 0 && (records || []).every(item => selectedBaseInventoryIds.has(item.id));
    if (selectAll) selectAll.checked = allSelected;
    if (selectAll) selectAll.indeterminate = selectedBaseInventoryIds.size > 0 && !allSelected;

    tbody.innerHTML = (records || []).map(item => `
        <tr>
            <td style="text-align:center;"><input type="checkbox" ${selectedBaseInventoryIds.has(item.id) ? 'checked' : ''} onchange="toggleBaseInventorySelect(${item.id})"></td>
            <td>${escapeHtml(item.material_code || '-')}</td>
            <td>${escapeHtml(item.region || '成都')}</td>
            <td>${escapeHtml(item.material_name || '-')}</td>
            <td>${escapeHtml(item.specification || '-')}</td>
            <td>${escapeHtml(item.detail_spec || '-')}</td>
            <td>${escapeHtml(item.unit_name || '-')}</td>
            <td>${item.quantity || 0}</td>
            <td>¥${Number(item.unit_price || 0).toFixed(2)}</td>
            <td>¥${(Number(item.quantity || 0) * Number(item.unit_price || 0)).toFixed(2)}</td>
            <td>${escapeHtml(item.update_time || '-')}</td>
            <td>${escapeHtml(item.remark || '-')}</td>
            <td><button class="btn btn-primary" style="padding:4px 10px;font-size:12px;" onclick="openBaseTransferModal(${item.id})">调拨到项目</button> <button class="btn btn-secondary" style="padding:4px 10px;font-size:12px;" onclick="editBaseInventory(${item.id})">编辑</button> <button class="btn btn-danger" style="padding:4px 10px;font-size:12px;" onclick="deleteBaseInventory(${item.id})">删除</button></td>
        </tr>
    `).join('') || '<tr><td colspan="13" class="loading">暂无基地库存，请点击"基地材料新增"补录历史材料</td></tr>';
}

function renderBaseTransferRecords(records) {
    const tbody = document.getElementById('baseTransferRecordsTable');
    const groups = groupBaseTransferRecords(records || []);
    tbody.innerHTML = groups.map(group => `
        <tr>
            <td><button class="btn btn-link" style="padding:0;font-size:13px;" onclick="viewBaseTransferBatch('${encodeURIComponent(group.key)}')">${escapeHtml(group.displayNo)}</button></td>
            <td>${escapeHtml(group.project_name || '-')}</td>
            <td>${escapeHtml(group.materialSummary || '-')}</td>
            <td>${Number(group.totalQuantity || 0).toFixed(2)}</td>
            <td>${group.itemCount}项</td>
            <td>¥${Number(group.originalTotal || 0).toFixed(2)}</td>
            <td>¥${Number(group.totalFreight || 0).toFixed(2)}</td>
            <td>¥${Number(group.depreciatedTotal || 0).toFixed(2)}</td>
            <td>${escapeHtml(group.operator_name || '-')}</td>
            <td>${escapeHtml(group.transfer_time || '-')}</td>
            <td><button class="btn btn-danger" style="padding:4px 10px;font-size:12px;" onclick="deleteBaseTransferBatch('${encodeURIComponent(group.key)}')">删除</button></td>
        </tr>
    `).join('') || '<tr><td colspan="11" class="loading">暂无基地调拨记录</td></tr>';
}

function getBaseTransferBatchKey(item) {
    if (item.batch_no) return `batch:${item.batch_no}`;
    return [
        item.project_id || '',
        item.project_name || '',
        item.operator_id || '',
        item.operator_name || '',
        item.transfer_time || '',
        item.remark || ''
    ].join('|');
}

function groupBaseTransferRecords(records) {
    const map = new Map();
    records.forEach(item => {
        const key = getBaseTransferBatchKey(item);
        if (!map.has(key)) {
            map.set(key, {
                key,
                displayNo: item.batch_no || item.transfer_no || '-',
                project_name: item.project_name,
                operator_name: item.operator_name,
                transfer_time: item.transfer_time,
                remark: item.remark,
                rows: [],
                totalQuantity: 0,
                totalFreight: 0,
                originalTotal: 0,
                depreciatedTotal: 0
            });
        }
        const group = map.get(key);
        const quantity = Number(item.quantity || 0);
        group.rows.push(item);
        group.totalQuantity += quantity;
        group.totalFreight += Number(item.freight || 0);
        group.originalTotal += quantity * Number(item.original_unit_price || 0);
        group.depreciatedTotal += quantity * Number(item.depreciated_unit_price || 0);
    });
    return Array.from(map.values()).map(group => {
        group.itemCount = group.rows.length;
        group.materialSummary = group.rows.length === 1
            ? group.rows[0].material_name
            : `${group.rows[0].material_name || '-'} 等${group.rows.length}项`;
        const transferNos = group.rows.map(row => row.transfer_no).filter(Boolean);
        if (!group.rows[0].batch_no && transferNos.length > 1) {
            group.displayNo = transferNos[0];
        }
        return group;
    });
}

function viewBaseTransferBatch(batchKey) {
    batchKey = decodeURIComponent(batchKey);
    const group = groupBaseTransferRecords(baseTransferRecordsCache).find(item => item.key === batchKey);
    if (!group) return;
    document.getElementById('detailTitle').textContent = `基地调拨详情 - ${group.displayNo}`;
    document.getElementById('detailContent').innerHTML = `
        <div class="card">
            <p><strong>调拨单号:</strong> ${escapeHtml(group.displayNo)}</p>
            <p><strong>目标项目:</strong> ${escapeHtml(group.project_name || '-')}</p>
            <p><strong>调拨时间:</strong> ${escapeHtml(group.transfer_time || '-')}</p>
            <p><strong>操作员:</strong> ${escapeHtml(group.operator_name || '-')}</p>
            <p><strong>备注:</strong> ${escapeHtml(group.remark || '-')}</p>
            <p><strong>运费:</strong> ¥${Number(group.totalFreight || 0).toFixed(2)}</p>
            <p><strong>折旧前总价:</strong> ¥${Number(group.originalTotal || 0).toFixed(2)}</p>
            <p><strong>折旧后总金额:</strong> ¥${Number(group.depreciatedTotal || 0).toFixed(2)}</p>
        </div>
        <h4 style="margin:15px 0;">调拨明细</h4>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>材料名称</th>
                        <th>规格</th>
                        <th>数量</th>
                        <th>原单价</th>
                        <th>折旧前总价</th>
                        <th>折旧后单价</th>
                        <th>折旧后金额</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${group.rows.map(item => `
                        <tr>
                            <td>${escapeHtml(item.material_name || '-')}</td>
                            <td>${escapeHtml(item.specification || '-')}</td>
                            <td>${item.quantity || 0}</td>
                            <td>¥${Number(item.original_unit_price || 0).toFixed(2)}</td>
                            <td>¥${(Number(item.quantity || 0) * Number(item.original_unit_price || 0)).toFixed(2)}</td>
                            <td>¥${Number(item.depreciated_unit_price || 0).toFixed(2)}</td>
                            <td>¥${(Number(item.quantity || 0) * Number(item.depreciated_unit_price || 0)).toFixed(2)}</td>
                            <td><button class="btn btn-secondary" style="padding:4px 10px;font-size:12px;margin-right:4px;" onclick="openEditBaseTransferModal(${item.id})">编辑</button><button class="btn btn-danger" style="padding:4px 10px;font-size:12px;" onclick="deleteBaseTransfer(${item.id})">删除</button></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
    openModal('modal-detail');
}

async function deleteBaseTransferBatch(batchKey) {
    batchKey = decodeURIComponent(batchKey);
    const group = groupBaseTransferRecords(baseTransferRecordsCache).find(item => item.key === batchKey);
    if (!group) return;
    if (!confirm(`确定要删除调拨单「${group.displayNo}」吗？删除后本批 ${group.rows.length} 条明细的基地库存将恢复。`)) return;
    for (const item of group.rows) {
        const res = await api(`/api/base-transfers/${item.id}`, { method: 'DELETE' });
        const data = await res.json();
        if (!data.success) {
            showToast(data.message || '删除失败', 'error');
            await loadBaseInventory();
            return;
        }
    }
    showToast('调拨单已删除，基地库存已恢复', 'success');
    await loadBaseInventory();
}
async function openBaseTransferModal(baseInventoryId) {
    const item = baseInventoryCache.find(record => record.id === baseInventoryId);
    if (!item) return;
    const res = await api('/api/projects?mine=1');
    const data = await res.json();
    const projects = data.success ? data.data || [] : [];
    document.getElementById('baseTransferInventoryId').value = item.id;
    document.getElementById('baseTransferMaterialName').value =
        `${item.material_name || ''}${item.specification ? ` / ${item.specification}` : ''}`;
    document.getElementById('baseTransferProject').innerHTML =
        '<option value="">-- 选择目标项目 --</option>' +
        projects.map(project => `<option value="${project.id}">${escapeHtml(project.project_name || '')}</option>`).join('');
    document.getElementById('baseTransferQuantity').value = Number(item.quantity || 0);
    document.getElementById('baseTransferQuantity').max = Number(item.quantity || 0);
    document.getElementById('baseTransferOriginalPrice').value = Number(item.unit_price || 0);
    document.getElementById('baseTransferDepreciatedPrice').value = Number(item.unit_price || 0);
    document.getElementById('baseTransferFreight').value = 0;
    document.getElementById('baseTransferRemark').value = '';
    openModal('modal-base-transfer');
}

async function submitBaseTransfer(event) {
    event.preventDefault();
    const baseInventoryId = parseInt(document.getElementById('baseTransferInventoryId').value);
    const body = {
        project_id: parseInt(document.getElementById('baseTransferProject').value),
        quantity: Number(document.getElementById('baseTransferQuantity').value),
        depreciated_unit_price: Number(document.getElementById('baseTransferDepreciatedPrice').value),
        freight: Number(document.getElementById('baseTransferFreight').value || 0),
        remark: document.getElementById('baseTransferRemark').value.trim()
    };
    if (!baseInventoryId || !body.project_id || body.quantity <= 0 || body.depreciated_unit_price < 0 || body.freight < 0) {
        showToast('请填写有效的项目、数量、折旧后单价和运费', 'warning');
        return;
    }
    try {
        const res = await api(`/api/base-inventory/${baseInventoryId}/transfer`, {
            method: 'POST',
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (!data.success) {
            showToast(data.message || '基地调拨失败', 'error');
            return;
        }
        closeModal('modal-base-transfer');
        showToast(`${data.message}，调拨金额 ¥${Number(data.total_amount || 0).toFixed(2)}`, 'success');
        await loadBaseInventory();
    } catch (e) {
        showToast('基地调拨失败', 'error');
    }
}

async function deleteBaseTransfer(transferId) {
    if (!confirm('确定要删除此调拨记录吗？删除后基地库存将恢复。')) return;
    try {
        const res = await api(`/api/base-transfers/${transferId}`, { method: 'DELETE' });
        const data = await res.json();
        if (!data.success) {
            showToast(data.message || '删除失败', 'error');
            return;
        }
        showToast(data.message, 'success');
        await loadBaseInventory();
    } catch (e) {
        showToast('删除调拨记录失败', 'error');
    }
}

async function openEditBaseTransferModal(transferId) {
    const item = baseTransferRecordsCache.find(r => r.id === transferId);
    if (!item) return;

    const res = await api('/api/projects?mine=1');
    const data = await res.json();
    const projects = data.success ? data.data || [] : [];
    document.getElementById('editBaseTransferProject').innerHTML =
        '<option value="">-- 选择目标项目 --</option>' +
        projects.map(p => `<option value="${p.id}" ${p.id === item.project_id ? 'selected' : ''}>${escapeHtml(p.project_name || '')}</option>`).join('');

    document.getElementById('editBaseTransferId').value = item.id;
    document.getElementById('editBaseTransferMaterialName').value = `${item.material_name || ''}${item.specification ? ' / ' + item.specification : ''}`;
    document.getElementById('editBaseTransferQuantity').value = item.quantity || 0;
    document.getElementById('editBaseTransferDepreciatedPrice').value = Number(item.depreciated_unit_price || 0);
    document.getElementById('editBaseTransferFreight').value = Number(item.freight || 0);
    document.getElementById('editBaseTransferRemark').value = item.remark || '';
    document.getElementById('editBaseTransferTime').value = (item.transfer_time || '').replace(' ', 'T').substring(0, 16);
    openModal('modal-base-transfer-edit');
}

async function submitEditBaseTransfer(event) {
    event.preventDefault();
    const transferId = parseInt(document.getElementById('editBaseTransferId').value);
    const body = {
        project_id: parseInt(document.getElementById('editBaseTransferProject').value),
        quantity: Number(document.getElementById('editBaseTransferQuantity').value),
        depreciated_unit_price: Number(document.getElementById('editBaseTransferDepreciatedPrice').value),
        freight: Number(document.getElementById('editBaseTransferFreight').value || 0),
        transfer_time: document.getElementById('editBaseTransferTime').value.replace('T', ' ') + ':00',
        remark: document.getElementById('editBaseTransferRemark').value.trim()
    };
    if (!transferId || !body.project_id || body.quantity <= 0 || body.depreciated_unit_price < 0 || body.freight < 0) {
        showToast('请填写有效的调拨信息', 'warning');
        return;
    }
    try {
        const res = await api(`/api/base-transfers/${transferId}`, {
            method: 'PUT',
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (!data.success) {
            showToast(data.message || '编辑调拨记录失败', 'error');
            return;
        }
        closeModal('modal-base-transfer-edit');
        showToast(data.message, 'success');
        await loadBaseInventory();
    } catch (e) {
        showToast('编辑调拨记录失败', 'error');
    }
}

function editBaseInventory(inventoryId) {
    const item = baseInventoryCache.find(r => r.id === inventoryId);
    if (!item) return;
    baseStockInEditId = inventoryId;
    document.getElementById('baseStockInMaterialId').value = item.material_id || '';
    document.getElementById('baseStockInMaterialName').value = item.material_name || '';
    document.getElementById('baseStockInSpecification').value = item.specification || '';
    document.getElementById('baseStockInDetailSpec').value = item.detail_spec || '';
    document.getElementById('baseStockInUnitName').value = item.unit_name || '';
    document.getElementById('baseStockInRegion').value = item.region || '成都';
    document.getElementById('baseStockInQuantity').value = item.quantity || 0;
    document.getElementById('baseStockInPrice').value = Number(item.unit_price || 0);
    document.getElementById('baseStockInRemark').value = item.remark || '';
    document.getElementById('baseStockInMaterialName').readOnly = false;
    document.getElementById('baseStockInSpecification').readOnly = false;
    document.getElementById('baseStockInDetailSpec').readOnly = false;
    document.getElementById('baseStockInUnitName').readOnly = false;
    document.querySelector('#modal-base-stock-in .modal-header h2').textContent = '基地材料编辑';
    openModal('modal-base-stock-in');
}

async function deleteBaseInventory(inventoryId) {
    if (!confirm('确定要删除此基地库存记录吗？')) return;
    try {
        const res = await api(`/api/base-inventory/${inventoryId}`, { method: 'DELETE' });
        const data = await res.json();
        if (!data.success) {
            showToast(data.message || '删除失败', 'error');
            return;
        }
        showToast(data.message, 'success');
        await loadBaseInventory();
    } catch (e) {
        showToast('删除基地库存失败', 'error');
    }
}

async function openBatchTransferModal() {
    if (selectedBaseInventoryIds.size === 0) {
        showToast('请先勾选要调拨的材料', 'warning');
        return;
    }
    const selectedItems = baseInventoryCache.filter(item => selectedBaseInventoryIds.has(item.id));
    if (selectedItems.length === 0) {
        showToast('选中的材料不存在，请刷新后重试', 'warning');
        return;
    }

    // 加载项目列表
    const res = await api('/api/projects?mine=1');
    const data = await res.json();
    const projects = data.success ? data.data || [] : [];
    document.getElementById('batchTransferProject').innerHTML =
        '<option value="">-- 选择目标项目 --</option>' +
        projects.map(project => `<option value="${project.id}">${escapeHtml(project.project_name || '')}</option>`).join('');

    // 渲染材料行
    document.getElementById('batchTransferItemsBody').innerHTML = selectedItems.map((item, idx) => `
        <tr data-batch-item-id="${item.id}">
            <td style="padding:6px;">${escapeHtml(item.material_name || '-')}</td>
            <td style="padding:6px;">${escapeHtml(item.region || '成都')}</td>
            <td style="padding:6px;">${escapeHtml(item.specification || '-')}</td>
            <td style="padding:6px;text-align:right;">${item.quantity || 0}</td>
            <td style="padding:6px;text-align:right;"><input type="number" class="batch-item-qty" min="0.01" step="0.01" max="${item.quantity || 0}" value="${item.quantity || 0}" style="width:80px;text-align:right;"></td>
            <td style="padding:6px;text-align:right;">¥${Number(item.unit_price || 0).toFixed(2)}</td>
            <td style="padding:6px;text-align:right;"><input type="number" class="batch-item-price" min="0" step="0.01" value="${Number(item.unit_price || 0).toFixed(2)}" style="width:80px;text-align:right;"></td>
        </tr>
    `).join('');

    document.getElementById('batchTransferFreight').value = 0;
    document.getElementById('batchTransferRemark').value = '';
    openModal('modal-batch-transfer');
}

async function submitBatchTransfer(event) {
    event.preventDefault();
    const projectId = parseInt(document.getElementById('batchTransferProject').value);
    if (!projectId) {
        showToast('请选择目标项目', 'warning');
        return;
    }

    const rows = document.querySelectorAll('#batchTransferItemsBody tr');
    const details = [];
    for (const row of rows) {
        const id = parseInt(row.dataset.batchItemId);
        const qtyInput = row.querySelector('.batch-item-qty');
        const priceInput = row.querySelector('.batch-item-price');
        if (isNaN(id) || !qtyInput || !priceInput) continue;
        const qty = Number(qtyInput.value);
        const price = Number(priceInput.value);
        if (isNaN(id) || isNaN(qty) || qty <= 0 || isNaN(price) || price < 0) {
            showToast('请填写每行的有效数量和折旧后单价', 'warning');
            return;
        }
        details.push({
            base_inventory_id: id,
            quantity: qty,
            depreciated_unit_price: price
        });
    }
    if (details.length === 0) {
        showToast('没有有效的调拨明细', 'warning');
        return;
    }

    const body = {
        project_id: projectId,
        freight: Number(document.getElementById('batchTransferFreight').value || 0),
        remark: document.getElementById('batchTransferRemark').value.trim(),
        details: details
    };

    try {
        const res = await api('/api/base-inventory/batch-transfer', {
            method: 'POST',
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (!data.success) {
            showToast(data.message || '批量调拨失败', 'error');
            return;
        }
        closeModal('modal-batch-transfer');
        showToast(data.message, 'success');
        await loadBaseInventory();
    } catch (e) {
        showToast('批量调拨失败', 'error');
    }
}

async function openBaseStockInModal(materialId = null, quantity = 1, unitPrice = 0, sourceWarehouseId = null) {
    baseStockInSourceWarehouseId = sourceWarehouseId;
    baseStockInEditId = null;
    document.querySelector('#modal-base-stock-in .modal-header h2').textContent = '基地材料新增';
    const fields = {
        materialName: document.getElementById('baseStockInMaterialName'),
        specification: document.getElementById('baseStockInSpecification'),
        detailSpec: document.getElementById('baseStockInDetailSpec'),
        unitName: document.getElementById('baseStockInUnitName')
    };
    let material = null;
    if (materialId) {
        await loadAllMaterialsForSelect();
        const source = allMaterialsCache.length > 0 ? allMaterialsCache : materials;
        material = source.find(item => item.id == materialId)
            || inventoryCache.find(item => item.material_id == materialId);
    }
    document.getElementById('baseStockInMaterialId').value = materialId || '';
    fields.materialName.value = material?.material_name || '';
    fields.specification.value = material?.specification || '';
    fields.detailSpec.value = material?.detail_spec || '';
    fields.unitName.value = material?.unit_name || '';
    Object.values(fields).forEach(field => { field.readOnly = Boolean(materialId); });
    document.getElementById('baseStockInQuantity').value = Number(quantity) > 0 ? Number(quantity) : 1;
    document.getElementById('baseStockInPrice').value = Number(unitPrice || 0);
    document.getElementById('baseStockInRegion').value = '成都';
    document.getElementById('baseStockInRemark').value = '';
    openModal('modal-base-stock-in');
}

async function submitBaseStockIn(event) {
    event.preventDefault();
    const materialId = parseInt(document.getElementById('baseStockInMaterialId').value) || null;
    const materialName = document.getElementById('baseStockInMaterialName').value.trim();
    const quantity = Number(document.getElementById('baseStockInQuantity').value);
    const unitPrice = Number(document.getElementById('baseStockInPrice').value || 0);
    if (!materialName || quantity <= 0) {
        showToast('请填写材料名称和有效数量', 'warning');
        return;
    }
    try {
        const body = {
            material_id: materialId,
            material_name: materialName,
            specification: document.getElementById('baseStockInSpecification').value.trim(),
            detail_spec: document.getElementById('baseStockInDetailSpec').value.trim(),
            unit_name: document.getElementById('baseStockInUnitName').value.trim(),
            region: document.getElementById('baseStockInRegion').value,
            quantity,
            unit_price: unitPrice,
            remark: document.getElementById('baseStockInRemark').value.trim(),
            source_warehouse_id: baseStockInSourceWarehouseId
        };
        const isEdit = baseStockInEditId !== null;
        const url = isEdit ? `/api/base-inventory/${baseStockInEditId}` : '/api/base-inventory';
        const method = isEdit ? 'PUT' : 'POST';
        const res = await api(url, { method, body: JSON.stringify(body) });
        const data = await res.json();
        if (!data.success) {
            showToast(data.message || (isEdit ? '编辑失败' : '入库基地失败'), 'error');
            return;
        }
        closeModal('modal-base-stock-in');
        baseStockInSourceWarehouseId = null;
        baseStockInEditId = null;
        showToast(data.message || (isEdit ? '已更新' : '已入库基地'), 'success');
        await Promise.all([loadBaseInventory(), loadInventory()]);
    } catch (e) {
        showToast(baseStockInEditId ? '编辑失败' : '入库基地失败', 'error');
    }
}

// ==================== 供应商管理 ====================

async function loadSuppliers() {
    try {
        const res = await api('/api/suppliers');
        const data = await res.json();
        if (data.success) {
            suppliers = data.data;
            renderSupplierTable();
            applyPermissionControls();
        }
    } catch (e) {
        showToast('加载供应商失败', 'error');
    }
}

function renderSupplierTable() {
    const tbody = document.getElementById('supplierTable');
    const rateMap = {0.01:'1%', 0.03:'3%', 0.06:'6%', 0.09:'9%', 0.13:'13%'};
    tbody.innerHTML = suppliers.map(s => {
        const rate = s.tax_rate !== undefined && s.tax_rate !== null ? (rateMap[s.tax_rate] || (s.tax_rate * 100).toFixed(0) + '%') : '-';
        return `
        <tr>
            <td>${escapeHtml(s.supplier_name)}</td>
            <td>${escapeHtml(s.contact || '-')}</td>
            <td>${escapeHtml(s.phone || '-')}</td>
            <td>${escapeHtml(s.account_username || '-')}</td>
            <td>${rate}</td>
            <td>
                <button class="btn btn-warning" style="padding:4px 12px;font-size:12px;" onclick="openEditSupplier(${s.id})">编辑</button>
            </td>
            <td class="admin-only">
                <button class="btn btn-danger" style="padding:4px 12px;font-size:12px;" onclick="deleteSupplier(${s.id})">删除</button>
            </td>
        </tr>
    `}).join('');
}

function openEditSupplier(id) {
    const s = suppliers.find(x => x.id === id);
    if (!s) return;
    document.getElementById('supplierId').value = s.id;
    document.getElementById('supplierName').value = s.supplier_name || '';
    document.getElementById('supplierContact').value = s.contact || '';
    document.getElementById('supplierPhone').value = s.phone || '';
    document.getElementById('supplierTaxRate').value = s.tax_rate !== null && s.tax_rate !== undefined ? String(s.tax_rate) : '';
    document.getElementById('supplierRemark').value = s.remark || '';
    document.getElementById('supplierModalTitle').textContent = '编辑供应商';
    openModal('modal-supplier');
}

function resetSupplierModal() {
    document.getElementById('supplierId').value = '';
    document.getElementById('supplierName').value = '';
    document.getElementById('supplierContact').value = '';
    document.getElementById('supplierPhone').value = '';
    document.getElementById('supplierTaxRate').value = '';
    document.getElementById('supplierRemark').value = '';
    document.getElementById('supplierModalTitle').textContent = '新建供应商';
}

async function deleteSupplier(id) {
    if (!confirm('确定要删除该供应商吗？')) return;

    try {
        const res = await api(`/api/suppliers/${id}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            showToast('删除成功', { credentials: 'same-origin' });
            loadSuppliers();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

document.getElementById('supplierForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('supplierId').value;
    const body = {
        supplier_name: document.getElementById('supplierName').value,
        contact: document.getElementById('supplierContact').value,
        phone: document.getElementById('supplierPhone').value,
        remark: document.getElementById('supplierRemark').value,
        tax_rate: document.getElementById('supplierTaxRate').value ? parseFloat(document.getElementById('supplierTaxRate').value) : null
    };

    try {
        const url = id ? `/api/suppliers/${id}` : '/api/suppliers';
        const method = id ? 'PUT' : 'POST';
        const res = await api(url, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            if (id) {
                showToast('更新成功', { credentials: 'same-origin' });
            } else if (data.username) {
                showToast(`创建成功，账号：${data.username}，初始密码：888888`, { credentials: 'same-origin' });
            } else {
                showToast('创建成功', { credentials: 'same-origin' });
            }
            closeModal('modal-supplier');
            resetSupplierModal();
            loadSuppliers();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('保存失败', 'error');
    }
});

// ==================== 对账管理 ====================

async function loadReconciliation() {
    try {
        const res = await api('/api/reconciliation');
        const data = await res.json();
        if (data.success) {
            renderReconciliationTable(data.data);
        }
    } catch (e) {
        showToast('加载对账单失败', 'error');
    }
}

function renderReconciliationTable(statements) {
    const tbody = document.getElementById('reconciliationTable');
    tbody.innerHTML = (statements || []).map(s => {
        const statusClass = s.status === '已打印' ? 'completed' : s.status === '已确认' ? 'approved' : 'pending';
        const isAdminUser = isAdmin();
        const canConfirm = s.status === '草稿' && isAdminUser;
        const canDelete = isAdminUser;
        const canRollback = (s.status === '已确认' || s.status === '已打印') && isAdminUser;
        const canPrint = s.status === '已确认' || s.status === '已打印';

        return `
        <tr>
            <td>${escapeHtml(s.statement_no || '')}</td>
            <td>${escapeHtml(s.supplier_name || '-')}</td>
            <td>${s.period_start || '-'} ~ ${s.period_end || '-'}</td>
            <td>¥${(s.total_amount || 0).toFixed(2)}</td>
            <td><span class="status ${statusClass}">${escapeHtml(s.status || '草稿')}</span></td>
            <td>
                <button class="btn btn-secondary" onclick="viewReconciliation(${s.id})" style="font-size:12px;padding:4px 10px;">查看</button>
                ${canConfirm ? `<button class="btn btn-warning" onclick="confirmReconciliation(${s.id})" style="font-size:12px;padding:4px 10px;">确认</button>` : ''}
                ${canRollback ? `<button class="btn btn-warning" onclick="rollbackReconciliation(${s.id})" style="font-size:12px;padding:4px 10px;">回退</button>` : ''}
                ${canPrint ? `<button class="btn btn-primary" onclick="printReconciliation(${s.id})" style="font-size:12px;padding:4px 10px;">打印</button>` : ''}
                ${canDelete ? `<button class="btn btn-danger" onclick="deleteReconciliation(${s.id})" style="font-size:12px;padding:4px 10px;">删除</button>` : ''}
            </td>
        </tr>`;
    }).join('') || '<tr><td colspan="6" class="loading">暂无数据</td></tr>';
}

async function viewReconciliation(id) {
    try {
        const res = await api(`/api/reconciliation/${id}`, { credentials: 'same-origin' });
        const data = await res.json();
        if (data.success) {
            const s = data.data;
            const details = data.details || [];
            document.getElementById('detailTitle').textContent = `对账单详情 - ${s.statement_no}`;
            document.getElementById('detailContent').innerHTML = `
                <div class="card">
                    <p><strong>单号:</strong> ${s.statement_no}</p>
                    <p><strong>供应商:</strong> ${s.supplier_name || '-'}</p>
                    <p><strong>客户:</strong> ${s.customer_name || '-'}</p>
                    <p><strong>项目:</strong> ${s.project_name || '-'}</p>
                    <p><strong>合同号:</strong> ${s.contract_no || '-'}</p>
                    <p><strong>期间:</strong> ${s.period_start || '-'} ~ ${s.period_end || '-'}</p>
                    <p><strong>结算金额:</strong> ¥${(s.total_amount || 0).toFixed(2)}</p>
                    <p><strong>不含税金额:</strong> ¥${(s.tax_exempt_amount || 0).toFixed(2)}</p>
                    <p><strong>累计已付款:</strong> ¥${(s.total_paid || 0).toFixed(2)}</p>
                    <p><strong>累计已开票:</strong> ¥${(s.total_invoiced || 0).toFixed(2)}</p>
                    <p><strong>累计已收款:</strong> ¥${(s.total_received || 0).toFixed(2)}</p>
                    <p><strong>截止本次尚欠:</strong> ¥${(s.balance_due || 0).toFixed(2)}</p>
                    <p><strong>状态:</strong> <span class="status ${s.status === '已确认' ? 'approved' : 'pending'}">${s.status}</span></p>
                </div>
                <h4 style="margin:15px 0;">对账明细</h4>
                <div class="table-container">
                    <table>
                        <thead><tr>
                            <th>原始单号</th><th>日期</th><th>材料</th>
                            <th>规格</th><th>单位</th><th>数量</th><th>单价</th><th>金额</th>
                        </tr></thead>
                        <tbody>
                            ${details.map(d => `
                                <tr>
                                    <td>${d.original_no}</td>
                                    <td>${d.transaction_date || '-'}</td>
                                    <td>${d.material_name || '-'}</td>
                                    <td>${d.specification || '-'}</td>
                                    <td>${d.unit_name || '-'}</td>
                                    <td>${d.quantity}</td>
                                    <td>¥${(d.unit_price || 0).toFixed(2)}</td>
                                    <td>¥${(d.amount || 0).toFixed(2)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
            openModal('modal-detail');
        }
    } catch (e) {
        showToast('加载详情失败', 'error');
    }
}

async function printReconciliation(id) {
    window.open(`/api/reconciliation/${id}/print`, '_blank');
    // 刷新列表以更新状态
    setTimeout(() => loadReconciliation(), 1000);
}

async function confirmReconciliation(id) {
    if (!confirm('确认此对账单？确认后可进行打印。')) return;
    try {
        const res = await api(`/api/reconciliation/${id}/confirm`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('对账单已确认', { credentials: 'same-origin' });
            loadReconciliation();
        } else {
            showToast(data.message || '操作失败', 'error');
        }
    } catch (e) {
        showToast('操作失败', 'error');
    }
}

async function deleteReconciliation(id) {
    if (!confirm('确定删除此对账单？删除后不可恢复。')) return;
    try {
        const res = await api(`/api/reconciliation/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            showToast('对账单已删除', { credentials: 'same-origin' });
            loadReconciliation();
        } else {
            showToast(data.message || '操作失败', 'error');
        }
    } catch (e) {
        showToast('操作失败', 'error');
    }
}

async function rollbackReconciliation(id) {
    if (!confirm('确定回退此对账单到草稿状态？')) return;
    try {
        const res = await api(`/api/reconciliation/${id}/rollback`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('对账单已回退到草稿', { credentials: 'same-origin' });
            loadReconciliation();
        } else {
            showToast(data.message || '操作失败', 'error');
        }
    } catch (e) {
        showToast('操作失败', 'error');
    }
}

// ==================== 对账单新建逻辑 ====================

let reconDetails = []; // 对账单明细数组

// 打开新建对账单模态框时，初始化下拉选项
async function initReconForm() {
    reconDetails = [];
    renderReconDetails();

    // 加载供应商（从API实时获取，不依赖全局变量）
    const supplierSelect = document.getElementById('reconSupplier');
    supplierSelect.innerHTML = '<option value="">--选择供应商--</option>';
    try {
        const supplierRes = await api('/api/suppliers');
        const supplierData = await supplierRes.json();
        if (supplierData.success !== false) {
            const supplierList = supplierData.data || [];
            // 同时更新全局变量
            suppliers = supplierList;
            supplierList.forEach(s => {
                supplierSelect.innerHTML += `<option value="${s.id}">${escapeHtml(s.supplier_name)}</option>`;
            });
        }
    } catch(e) {
        console.error('加载供应商失败:', e);
    }

    // 加载项目（只显示当前用户绑定的项目）
    try {
        const res = await api('/api/projects?mine=1');
        const data = await res.json();
        const projectSelect = document.getElementById('reconProject');
        projectSelect.innerHTML = '<option value="">--选择项目--</option>';
        (data.data || []).forEach(p => {
            projectSelect.innerHTML += `<option value="${p.id}">${escapeHtml(p.project_name)}</option>`;
        });
    } catch(e) {}

    // 重置表单
    document.getElementById('reconContract').value = '';
    document.getElementById('reconPeriodStart').value = '';
    document.getElementById('reconPeriodEnd').value = '';
    document.getElementById('reconTaxRate').value = '0.01';
    document.getElementById('reconTotalPaid').value = '0';
    document.getElementById('reconTotalInvoiced').value = '0';
    document.getElementById('reconTotalReceived').value = '0';
    document.getElementById('reconRemark').value = '';
    document.getElementById('reconCustomer').value = '中天建设集团有限公司';
    calcReconAmount();
}

// 供应商或周期变化时，自动查询采购记录填充明细
async function onReconFilterChange() {
    const supplierId = document.getElementById('reconSupplier').value;
    const periodStart = document.getElementById('reconPeriodStart').value;
    const periodEnd = document.getElementById('reconPeriodEnd').value;

    if (!supplierId) {
        reconDetails = [];
        renderReconDetails();
        calcReconAmount();
        return;
    }

    // 如果周期不完整，等用户选完
    if (!periodStart || !periodEnd) {
        return;
    }

    try {
        const params = new URLSearchParams({ supplier_id: supplierId });
        if (periodStart) params.set('period_start', periodStart);
        if (periodEnd) params.set('period_end', periodEnd);

        const res = await api(`/api/reconciliation/supplier-purchases?${params}`, { credentials: 'same-origin' });
        const data = await res.json();
        if (!data.success) {
            showToast('查询采购记录失败', 'error');
            return;
        }

        // 将查询结果转换为对账明细
        reconDetails = (data.data || []).map(row => ({
            transaction_date: row.inquiry_date || (row.inquiry_create_time ? row.inquiry_create_time.split(' ')[0] : ''),
            original_no: '',  // 原始单号留空，用户自己填
            inquiry_no: row.inquiry_no || '',  // 询价单号，仅供参考显示
            material_id: row.material_id,
            material_name: row.material_name || '-',
            specification: row.specification || '-',
            unit_name: row.unit_name || '-',
            quantity: row.quantity || 0,
            unit_price: row.tax_price || 0,
            amount: row.total_amount || (row.tax_price || 0) * (row.quantity || 0),
            remark: ''
        }));

        renderReconDetails();
        calcReconAmount();

        if (reconDetails.length > 0) {
            showToast(`已自动填充 ${reconDetails.length} 条采购记录`, { credentials: 'same-origin' });
        } else {
            showToast('该供应商在指定周期内无采购记录', 'warning');
        }
    } catch(e) {
        console.error('查询采购记录失败:', e);
        showToast('查询采购记录失败', 'error');
    }
}

// 手动添加行
function addReconDetailRow() {
    reconDetails.push({
        transaction_date: '',
        original_no: '',
        material_name: '',
        specification: '',
        unit_name: '',
        quantity: 0,
        unit_price: 0,
        amount: 0,
        remark: ''
    });
    renderReconDetails();
}

// 删除行
function removeReconDetailRow(index) {
    reconDetails.splice(index, 1);
    renderReconDetails();
    calcReconAmount();
}

// 更新行字段
function updateReconDetailField(index, field, value) {
    if (!reconDetails[index]) return;
    reconDetails[index][field] = value;
    // 数量或单价变化时自动计算金额
    if (field === 'quantity' || field === 'unit_price') {
        reconDetails[index].amount = (parseFloat(reconDetails[index].quantity) || 0) * (parseFloat(reconDetails[index].unit_price) || 0);
    }
    renderReconDetails();
    calcReconAmount();
}

// 渲染明细表格
function renderReconDetails() {
    const tbody = document.getElementById('reconDetailsBody');
    if (!reconDetails || reconDetails.length === 0) {
        tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;color:#999;">请选择供应商和对账周期，自动填充采购记录</td></tr>';
        return;
    }

    tbody.innerHTML = reconDetails.map((d, i) => `
        <tr>
            <td style="text-align:center;">${i + 1}</td>
            <td><input type="date" value="${d.transaction_date || ''}" onchange="updateReconDetailField(${i}, 'transaction_date', this.value)" style="width:110px;"></td>
            <td><input type="text" value="${escapeHtml(d.original_no || '')}" onchange="updateReconDetailField(${i}, 'original_no', this.value)" placeholder="填写原始单号" style="width:120px;"></td>
            <td style="color:var(--text-muted);font-size:12px;white-space:nowrap;">${escapeHtml(d.inquiry_no || '')}</td>
            <td>${escapeHtml(d.material_name || '')}</td>
            <td>${escapeHtml(d.specification || '')}</td>
            <td>${escapeHtml(d.unit_name || '')}</td>
            <td>${d.quantity || 0}</td>
            <td>¥${(d.unit_price || 0).toFixed(2)}</td>
            <td style="font-weight:500;">¥${(d.amount || 0).toFixed(2)}</td>
            <td><input type="text" value="${escapeHtml(d.remark || '')}" onchange="updateReconDetailField(${i}, 'remark', this.value)" style="width:70px;"></td>
            <td><button type="button" class="btn btn-danger btn-sm" onclick="removeReconDetailRow(${i})" style="padding:2px 8px;">×</button></td>
        </tr>
    `).join('');
}

// 计算金额汇总
function calcReconAmount() {
    let total = 0;
    reconDetails.forEach(d => { total += parseFloat(d.amount) || 0; });

    const taxRate = parseFloat(document.getElementById('reconTaxRate').value) || 0.01;
    const taxExempt = total / (1 + taxRate);

    document.getElementById('reconTotalAmount').textContent = `¥${total.toFixed(2)}`;
    document.getElementById('reconTaxExemptAmount').textContent = `¥${taxExempt.toFixed(2)}`;
}

// 提交对账单
async function submitReconciliationForm(e) {
    e.preventDefault();

    if (reconDetails.length === 0) {
        showToast('请添加对账明细', 'warning');
        return;
    }

    const statementNo = document.getElementById('reconStatementNo').value.trim();
    if (!statementNo) {
        showToast('请输入对账单号', 'warning');
        return;
    }

    const supplierId = document.getElementById('reconSupplier').value;
    if (!supplierId) {
        showToast('请选择供货单位', 'warning');
        return;
    }

    const totalPaid = parseFloat(document.getElementById('reconTotalPaid').value) || 0;
    const totalInvoiced = parseFloat(document.getElementById('reconTotalInvoiced').value) || 0;
    const totalReceived = parseFloat(document.getElementById('reconTotalReceived').value) || 0;
    const taxRate = parseFloat(document.getElementById('reconTaxRate').value) || 0.01;

    let totalAmount = 0;
    reconDetails.forEach(d => { totalAmount += parseFloat(d.amount) || 0; });
    const balanceDue = totalAmount - totalPaid;

    const payload = {
        reconciliation_no: statementNo,
        supplier_id: parseInt(supplierId),
        customer_name: document.getElementById('reconCustomer').value,
        project_id: parseInt(document.getElementById('reconProject').value) || null,
        contract_no: document.getElementById('reconContract').value,
        period_start: document.getElementById('reconPeriodStart').value,
        period_end: document.getElementById('reconPeriodEnd').value,
        total_paid: totalPaid,
        total_invoiced: totalInvoiced,
        total_received: totalReceived,
        balance_due: balanceDue,
        remark: document.getElementById('reconRemark').value,
        details: reconDetails.map(d => ({
            transaction_date: d.transaction_date,
            original_no: d.original_no,
            material_name: d.material_name,
            specification: d.specification,
            unit_name: d.unit_name,
            quantity: parseFloat(d.quantity) || 0,
            unit_price: parseFloat(d.unit_price) || 0,
            amount: parseFloat(d.amount) || 0,
            remark: d.remark || ''
        }))
    };

    try {
        const res = await api('/api/reconciliation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            showToast('对账单创建成功！', { credentials: 'same-origin' });
            closeModal('modal-reconciliation');
            loadReconciliation();
        } else {
            showToast(data.message || '创建失败', 'error');
        }
    } catch(e) {
        showToast('网络错误，请重试', 'error');
    }
}

// Toast 提示
function showToast(msg, type = 'info') {
    let toast = document.getElementById('toast-container');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast-container';
        toast.style.cssText = 'position:fixed;top:20px;right:20px;z-index:10000;display:flex;flex-direction:column;gap:8px;';
        document.body.appendChild(toast);
    }
    const colors = { success: '#27ae60', error: '#e74c3c', warning: '#f39c12', info: '#3498db' };
    const el = document.createElement('div');
    el.style.cssText = `padding:10px 20px;border-radius:6px;color:#fff;font-size:14px;background:${colors[type] || colors.info};box-shadow:0 2px 8px rgba(0,0,0,0.15);animation:fadeIn 0.3s;`;
    el.textContent = msg;
    toast.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; setTimeout(() => el.remove(), 300); }, 3000);
}

// ==================== 字典数据本地缓存 ====================

const CACHE_TTL = 30 * 60 * 1000; // 30分钟缓存

function getCache(key) {
    try {
        const cached = localStorage.getItem(key);
        if (!cached) return null;
        const { data, timestamp } = JSON.parse(cached);
        if (Date.now() - timestamp > CACHE_TTL) {
            localStorage.removeItem(key);
            return null;
        }
        return data;
    } catch {
        return null;
    }
}

function setCache(key, data) {
    try {
        localStorage.setItem(key, JSON.stringify({ data, timestamp: Date.now() }));
    } catch (e) {
        console.warn('缓存写入失败', e);
    }
}

function loadCacheOrFetch(key, url) {
    const cached = getCache(key);
    if (cached) {
        return Promise.resolve({ success: true, data: cached, fromCache: true });
    }
    return api(url).then(res => res.json()).then(data => {
        if (data.success) {
            setCache(key, data.data);
        }
        return { ...data, fromCache: false };
    });
}

// 清除字典缓存（登录后、增删改后调用）
function clearDictCache() {
    const keys = ['dict_units', 'dict_suppliers', 'dict_customers', 'dict_roles'];
    keys.forEach(k => localStorage.removeItem(k));
}

// ==================== 辅助函数 ====================

async function loadUnitsAndSuppliers() {
    if (suppliers && suppliers.length > 0) return;
    try {
        const supRes = await api('/api/suppliers');
        const supData = await supRes.json();
        suppliers = supData.success ? supData.data : [];
        console.log('加载供应商:', suppliers.length, '个');

        const optHtml = '<option value="">--请选择--</option>' + 
            suppliers.map(s => `<option value="${s.id}">${s.supplier_name}</option>`).join('');

        const supSelect = document.getElementById('materialSupplier');
        if (supSelect) {
            supSelect.innerHTML = optHtml;
        }

        const stockInSup = document.getElementById('stockInSupplier');
        if (stockInSup) {
            stockInSup.innerHTML = optHtml;
        }
    } catch (e) {
        console.error('加载供应商失败:', e);
    }
}

async function loadAllMaterialsForSelect() {
    try {
        const res = await api('/api/materials?page=1&page_size=9999');
        const data = await res.json();
        if (data.success) {
            allMaterialsCache = data.data || [];
            console.log('加载全部材料:', allMaterialsCache.length, '个');
        }
    } catch (e) {
        console.error('加载全部材料失败:', e);
    }
}

// ==================== 询价单明细操作（嵌套比价结构）====================

function buildDefaultQuotes() {
    const user = JSON.parse(sessionStorage.getItem('currentUser') || '{}');
    const defaultNames = user.username === 'liuruitao'
        ? ['云南海博鸿运商贸有限公司', '成都市涵婷商贸有限公司', '成都市鑫繁江金属制品有限公司']
        : ['永炜鑫', '灿宝', '蓉心胜'];
    return defaultNames.map(name => {
        const s = (suppliers || []).find(x => (x.supplier_name || '').includes(name));
        return {
            supplier_id: s ? s.id : '',
            supplier_name: s ? s.supplier_name : '',
            tax_price: 0, tax_exempt_price: 0, tax_rate: (s && s.tax_rate != null) ? s.tax_rate : 0.01, total_amount: 0, is_lowest: false, is_selected: false
        };
    });
}

function makeEmptyQuote() {
    return {
        supplier_id: '', supplier_name: '',
        tax_price: 0, tax_exempt_price: 0, tax_rate: 0.01,
        total_amount: 0, is_lowest: false, is_selected: false
    };
}

function addQuoteToItem(itemIndex) {
    const item = inquiryItems[itemIndex];
    if (!item) return;
    item.quotes.push(makeEmptyQuote());
    renderInquiryItems();
}

function removeQuoteFromItem(itemIndex, quoteIndex) {
    const item = inquiryItems[itemIndex];
    if (!item || item.quotes.length <= 1) return;
    const quote = item.quotes[quoteIndex];
    const name = quote && quote.supplier_name ? quote.supplier_name : '该供应商';
    if (!confirm(`确定要删除"${name}"的报价吗？`)) return;
    item.quotes.splice(quoteIndex, 1);
    updateLowestFlag(itemIndex);
    renderInquiryItems();
    updateInquiryTotal();
}

function addInquiryItem() {
    const item = {
        material_id: '',
        material_name: '',
        material_code: '',
        specification: '',
        detail_spec: '',
        brand: '',
        unit_name: '',
        quantity: 1,
        library_price: 0,
        tax_price: 0,
        cash_price: 0,
        selected_quote_id: null,
        is_national_standard: null,
        is_cash_price: 0,
        quotes: buildDefaultQuotes()
    };
    inquiryItems.push(item);
    renderInquiryItems();
}

function removeInquiryItem(itemIndex) {
    inquiryItems.splice(itemIndex, 1);
    renderInquiryItems();
    updateInquiryTotal();
}

function onMaterialSelect(itemIndex, materialId) {
    const item = inquiryItems[itemIndex];
    const m = (allMaterialsCache.length > 0 ? allMaterialsCache : materials || []).find(x => x?.id == materialId);
    if (m) {
        item.material_id = m.id;
        item.material_name = m.material_name || '';
        item.material_code = m.material_code || '';
        item.specification = m.specification || '';
        item.detail_spec = m.detail_spec || '';
        item.brand = m.brand || '';
        item.unit_name = m.unit_name || '';
        // 保存两种价格，库内价根据是否现金含税价选择
        item.tax_price = m.tax_price || 0;
        item.cash_price = m.cash_price || 0;
        item.library_price = item.is_cash_price === 1 ? item.cash_price : item.tax_price;
    }
    renderInquiryItems();
}

function updateQuoteFieldLive(itemIndex, quoteIndex, value) {
    const item = inquiryItems[itemIndex];
    if (!item || !item.quotes[quoteIndex]) return;
    const quote = item.quotes[quoteIndex];
    const numValue = parseFloat(value) || 0;
    quote.tax_price = roundMoney(numValue);
    quote.tax_exempt_price = numValue > 0 ? roundMoney(numValue / (1 + quote.tax_rate)) : 0;
    quote.total_amount = roundMoney(numValue * item.quantity);
    // 局部更新 DOM，不重建
    const row = document.querySelector(`.quote-row[data-item="${itemIndex}"][data-quote="${quoteIndex}"]`);
    if (row) {
        const exemptInput = row.querySelector('.quote-tax-exempt');
        if (exemptInput) exemptInput.value = quote.tax_exempt_price ? quote.tax_exempt_price.toFixed(2) : '';
        const totalInput = row.querySelector('.quote-total-amount');
        if (totalInput) totalInput.value = '¥' + (quote.total_amount || 0).toFixed(2);
        // 库内价差额提示
        const diffHint = row.querySelector('.price-diff-hint');
        if (diffHint) {
            const diff = numValue - parseFloat(item.library_price || 0);
            const pct = item.library_price > 0 ? ((diff / item.library_price) * 100).toFixed(1) : '';
            const color = diff < 0 ? 'var(--success)' : diff > 0 ? 'var(--danger)' : 'var(--text-muted)';
            const arrow = diff < 0 ? '↓' : diff > 0 ? '↑' : '=';
            diffHint.style.color = color;
            diffHint.textContent = numValue > 0 ? `比库内价 ${arrow} ¥${Math.abs(diff).toFixed(2)}${pct ? ' (' + pct + '%)' : ''}` : '';
        }
    }
    // 最低价标记也用局部更新，不走完整渲染
    updateLowestBadgeDOM(itemIndex);
    updateInquiryTotal();
}

// 局部更新最低价标记，避免完整重渲染
function updateLowestBadgeDOM(itemIndex) {
    const item = inquiryItems[itemIndex];
    if (!item) return;
    const validQuotes = item.quotes.filter(q => q.supplier_id && q.tax_price > 0);
    item.quotes.forEach(q => q.is_lowest = false);
    if (validQuotes.length > 0) {
        const lowest = validQuotes.reduce((min, q) =>
            (q.tax_exempt_price || 0) < (min.tax_exempt_price || 0) ? q : min, validQuotes[0]);
        lowest.is_lowest = true;
    }
    // 只更新该 item 下所有报价行的样式
    const rows = document.querySelectorAll(`.quote-row[data-item="${itemIndex}"]`);
    rows.forEach(r => {
        const qi = parseInt(r.dataset.quote);
        const q = item.quotes[qi];
        if (!q) return;
        r.classList.toggle('lowest', !!q.is_lowest);
        const existingBadge = r.querySelector('.lowest-badge');
        if (q.is_lowest) {
            if (!existingBadge) {
                const badge = document.createElement('div');
                badge.className = 'lowest-badge';
                badge.textContent = '最低价';
                r.prepend(badge);
            }
        } else {
            if (existingBadge) existingBadge.remove();
        }
    });
}

function updateQuoteField(itemIndex, quoteIndex, field, value) {
    const item = inquiryItems[itemIndex];
    if (!item || !item.quotes[quoteIndex]) return;

    const quote = item.quotes[quoteIndex];
    const numValue = parseFloat(value) || 0;

    quote[field] = numValue;

    // 自动计算不含税单价和总金额
    if (field === 'tax_price') {
        quote.tax_price = roundMoney(numValue);
        quote.tax_exempt_price = numValue > 0 ? roundMoney(numValue / (1 + quote.tax_rate)) : 0;
        quote.total_amount = roundMoney(numValue * item.quantity);
    } else if (field === 'tax_rate') {
        quote.tax_exempt_price = quote.tax_price > 0 ? roundMoney(quote.tax_price / (1 + numValue)) : 0;
        quote.total_amount = roundMoney(quote.tax_price * item.quantity);
    } else if (field === 'tax_exempt_price') {
        quote.tax_exempt_price = roundMoney(numValue);
    }

    // 局部更新当前报价行 DOM（税率/不含税价变更时需要同步显示）
    const row = document.querySelector(`.quote-row[data-item="${itemIndex}"][data-quote="${quoteIndex}"]`);
    if (row) {
        if (field === 'tax_rate' || field === 'tax_exempt_price') {
            const exemptInput = row.querySelector('.quote-tax-exempt');
            if (exemptInput) exemptInput.value = quote.tax_exempt_price ? quote.tax_exempt_price.toFixed(2) : '';
            const totalInput = row.querySelector('.quote-total-amount');
            if (totalInput) totalInput.value = '¥' + (quote.total_amount || 0).toFixed(2);
            // 同步含税单价输入框
        }
    }

    // 局部更新最低价标记，避免完整重渲染
    updateLowestBadgeDOM(itemIndex);
    updateInquiryTotal();
}

function updateItemField(itemIndex, field, value) {
    const item = inquiryItems[itemIndex];
    if (item) {
        item[field] = value;
    }
}

function onInquiryCashPriceChange(itemIndex, value) {
    const item = inquiryItems[itemIndex];
    if (!item) return;
    item.is_cash_price = value;

    // 更新库内价：现金含税价材料显示现金含税价，否则显示含税价
    const m = (allMaterialsCache.length > 0 ? allMaterialsCache : materials || []).find(x => x?.id == item.material_id);
    if (m) {
        item.tax_price = m.tax_price || 0;
        item.cash_price = m.cash_price || 0;
        item.library_price = value === 1 ? item.cash_price : item.tax_price;
    }

    // 如果选择了现金含税价，所有报价的税率默认为1%
    if (value === 1) {
        item.quotes.forEach(q => {
            q.tax_rate = 0.01;
            if (q.tax_price > 0) {
                q.tax_exempt_price = q.tax_price / (1 + 0.01);
            }
        });
    }

    // 局部更新该 item 的 DOM
    const itemCard = document.querySelectorAll('.inquiry-item-card')[itemIndex];
    if (itemCard) {
        // 更新库内价徽章
        const badge = itemCard.querySelector('.library-price-badge');
        if (badge) badge.textContent = `库内价: 含税 ¥${(item.tax_price || 0).toFixed(2)} / 现金含税 ¥${(item.cash_price || 0).toFixed(2)}`;
        // 更新所有报价行的标签、不含税单价、税率和差额提示
        const rows = itemCard.querySelectorAll('.quote-row');
        rows.forEach(r => {
            const qi = parseInt(r.dataset.quote);
            const q = item.quotes[qi];
            if (!q) return;
            // 含税单价/现金含税价标签
            const priceLabel = r.querySelector('.quote-inputs .input-group label');
            if (priceLabel) priceLabel.textContent = value == 1 ? '现金含税价' : '含税单价';
            const exemptInput = r.querySelector('.quote-tax-exempt');
            if (exemptInput) exemptInput.value = q.tax_exempt_price ? q.tax_exempt_price.toFixed(2) : '';
            const rateSelect = r.querySelector('.quote-inputs select');
            if (rateSelect) rateSelect.value = q.tax_rate;
            // 库内价差额提示
            const diffHint = r.querySelector('.price-diff-hint');
            if (diffHint && q.tax_price > 0) {
                const diff = parseFloat(q.tax_price) - parseFloat(item.library_price || 0);
                const pct = item.library_price > 0 ? ((diff / item.library_price) * 100).toFixed(1) : '';
                const color = diff < 0 ? 'var(--success)' : diff > 0 ? 'var(--danger)' : 'var(--text-muted)';
                const arrow = diff < 0 ? '↓' : diff > 0 ? '↑' : '=';
                diffHint.style.color = color;
                diffHint.textContent = `比库内价 ${arrow} ¥${Math.abs(diff).toFixed(2)}${pct ? ' (' + pct + '%)' : ''}`;
            }
        });
    }
    updateInquiryTotal();
}

function updateItemQuantity(itemIndex, quantity) {
    const item = inquiryItems[itemIndex];
    item.quantity = parseFloat(quantity) || 1;

    // 重新计算所有报价的总金额并局部更新 DOM
    const rows = document.querySelectorAll(`.quote-row[data-item="${itemIndex}"]`);
    rows.forEach(r => {
        const qi = parseInt(r.dataset.quote);
        const q = item.quotes[qi];
        if (!q) return;
        q.total_amount = (q.tax_price || 0) * item.quantity;
        const totalInput = r.querySelector('.quote-total-amount');
        if (totalInput) totalInput.value = '¥' + (q.total_amount || 0).toFixed(2);
    });

    updateLowestBadgeDOM(itemIndex);
    updateInquiryTotal();
}

function updateLowestFlag(itemIndex) {
    const item = inquiryItems[itemIndex];
    const validQuotes = item.quotes.filter(q => q.supplier_id && q.tax_price > 0);

    // 重置所有报价的 is_lowest 标记
    item.quotes.forEach(q => q.is_lowest = false);

    if (validQuotes.length === 0) return;

    // 找出最低价（基于不含税单价）
    const lowest = validQuotes.reduce((min, q) =>
        (q.tax_exempt_price || 0) < (min.tax_exempt_price || 0) ? q : min, validQuotes[0]);
    lowest.is_lowest = true;
}

function selectQuote(itemIndex, quoteIndex) {
    const item = inquiryItems[itemIndex];

    // 重置所有选中状态
    item.quotes.forEach(q => q.is_selected = false);
    item.quotes[quoteIndex].is_selected = true;
    item.selected_quote_id = item.quotes[quoteIndex].supplier_id;

    // 局部更新按钮样式，避免完整重渲染
    const rows = document.querySelectorAll(`.quote-row[data-item="${itemIndex}"]`);
    rows.forEach(r => {
        const qi = parseInt(r.dataset.quote);
        const q = item.quotes[qi];
        if (!q) return;
        r.classList.toggle('selected', !!q.is_selected);
        const btn = r.querySelector('.quote-actions .quote-select-btn');
        if (btn) {
            btn.className = `btn quote-select-btn ${q.is_selected ? 'btn-primary' : 'btn-outline'}`;
            btn.textContent = q.is_selected ? '已选定' : '设为拟定';
        }
    });
    updateInquiryTotal();
}

function updateQuoteSupplier(itemIndex, quoteIndex, supplierId) {
    const item = inquiryItems[itemIndex];
    const quote = item.quotes[quoteIndex];

    const supplier = (suppliers || []).find(s => s.id == supplierId);
    quote.supplier_id = supplierId;
    quote.supplier_name = supplier ? supplier.supplier_name : '';

    updateLowestBadgeDOM(itemIndex);
    updateInquiryTotal();
}

// ==================== 供应商模糊匹配下拉框 ====================

// ==================== 材料选择弹出面板 ====================

let materialPickerItemIndex = null; // 当前正在选择材料的 itemIndex

function openMaterialPicker(input, itemIndex) {
    materialPickerItemIndex = itemIndex;
    // 清空搜索条件
    document.getElementById('mpSearch').value = '';
    document.getElementById('mpSpec').value = '';
    document.getElementById('mpBrand').value = '';
    // 显示面板
    document.getElementById('materialPickerOverlay').classList.add('show');
    document.getElementById('materialPickerPanel').classList.add('show');
    // 渲染材料列表
    renderMaterialPickerList();
    // 聚焦搜索框
    setTimeout(() => document.getElementById('mpSearch').focus(), 100);
}

function closeMaterialPicker() {
    document.getElementById('materialPickerOverlay').classList.remove('show');
    document.getElementById('materialPickerPanel').classList.remove('show');
    materialPickerItemIndex = null;
}

function filterMaterialPicker() {
    renderMaterialPickerList();
}

function clearMaterialPickerFilters() {
    document.getElementById('mpSearch').value = '';
    document.getElementById('mpSpec').value = '';
    document.getElementById('mpBrand').value = '';
    renderMaterialPickerList();
    document.getElementById('mpSearch').focus();
}

function renderMaterialPickerList() {
    const validMaterials = (allMaterialsCache.length > 0 ? allMaterialsCache : materials) || [];
    const keyword = (document.getElementById('mpSearch')?.value || '').trim().toLowerCase();
    const specFilter = (document.getElementById('mpSpec')?.value || '').trim().toLowerCase();
    const brandFilter = (document.getElementById('mpBrand')?.value || '').trim().toLowerCase();

    let filtered = validMaterials;
    if (keyword) {
        filtered = filtered.filter(m => {
            const name = (m.material_name || '').toLowerCase();
            const code = (m.material_code || '').toLowerCase();
            const spec = (m.specification || '').toLowerCase();
            return name.includes(keyword) || code.includes(keyword) || spec.includes(keyword);
        });
    }
    if (specFilter) {
        filtered = filtered.filter(m => (m.specification || '').toLowerCase().includes(specFilter));
    }
    if (brandFilter) {
        filtered = filtered.filter(m => (m.brand || '').toLowerCase().includes(brandFilter));
    }

    // 限制显示前200条
    const display = filtered.slice(0, 200);
    const list = document.getElementById('mpList');
    if (!list) return;

    if (display.length === 0) {
        list.innerHTML = '<div style="padding:30px;text-align:center;color:#999;">无匹配材料</div>';
        return;
    }

    list.innerHTML = display.map(m => {
        const code = m.material_code || '';
        const regionCode = (code.substring(0, 2) || '').toUpperCase();
        const region = codeToRegion(code);
        const name = escapeHtml(m.material_name || '');
        const spec = escapeHtml(m.specification || '');
        const brand = escapeHtml(m.brand || '');
        const unit = escapeHtml(m.unit_name || '');
        const taxPrice = (m.tax_price || 0).toFixed(2);
        const cashPrice = (m.cash_price || 0).toFixed(2);
        const isSelected = materialPickerItemIndex !== null
            && inquiryItems[materialPickerItemIndex]
            && inquiryItems[materialPickerItemIndex].material_id == m.id;

        return `<div class="mp-item ${isSelected ? 'mp-selected' : ''}"
                     onclick="selectMaterialFromPicker(${m.id})"
                     style="display:flex;align-items:center;gap:10px;padding:10px 16px;cursor:pointer;border-bottom:1px solid #f0f0f0;transition:background 0.15s;">
            <div style="flex:1;min-width:0;">
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;">
                    <span style="font-size:11px;color:#fff;background:${regionCode === 'AN' ? '#1976d2' : regionCode === 'KM' ? '#e65100' : regionCode === 'BN' ? '#2e7d32' : regionCode === 'DL' ? '#6a1b9a' : regionCode === 'YX' ? '#c62828' : regionCode === 'CD' ? '#00838f' : regionCode === 'GX' ? '#16a34a' : '#999'};padding:1px 6px;border-radius:3px;flex-shrink:0;">${region || '??'}</span>
                    <strong style="font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${name}</strong>
                    ${spec ? `<span style="color:#666;font-size:12px;flex-shrink:0;">${spec}</span>` : ''}
                </div>
                <div style="display:flex;gap:12px;font-size:11px;color:#999;">
                    <span>编码: ${escapeHtml(code)}</span>
                    ${brand ? `<span>品牌: ${brand}</span>` : ''}
                    ${unit ? `<span>单位: ${unit}</span>` : ''}
                </div>
            </div>
            <div style="text-align:right;flex-shrink:0;">
                <div style="font-size:12px;color:#333;">含税 <strong style="color:#e74c3c;">¥${taxPrice}</strong></div>
                <div style="font-size:11px;color:#999;">现金含税 ¥${cashPrice}</div>
            </div>
            ${isSelected ? '<div style="color:#27ae60;font-size:18px;">✓</div>' : ''}
        </div>`;
    }).join('');

    if (filtered.length > 200) {
        list.innerHTML += `<div style="padding:10px;text-align:center;color:#999;font-size:12px;">仅显示前200条，请缩小搜索范围</div>`;
    }
}

function selectMaterialFromPicker(materialId) {
    if (materialPickerItemIndex === null) return;
    onMaterialSelect(materialPickerItemIndex, materialId);
    closeMaterialPicker();
    // 更新输入框显示
    const item = inquiryItems[materialPickerItemIndex];
    if (item) {
        const picker = document.querySelector(`.material-picker[data-item="${materialPickerItemIndex}"]`);
        if (picker) {
            const input = picker.querySelector('.material-picker-input');
            const hiddenId = picker.querySelector('.material-picker-id');
            if (input) input.value = (item.material_code || '') + ' ' + (item.material_name || '') + (item.specification ? ' ' + item.specification : '');
            if (hiddenId) hiddenId.value = materialId;
        }
    }
}

// ==================== 供应商可搜索下拉框 ====================

function filterSupplierDropdown(input, itemIndex, quoteIndex) {
    const combobox = input.closest('.supplier-combobox');
    const list = combobox.querySelector('.supplier-combo-list');
    const hiddenId = combobox.querySelector('.supplier-combo-id');
    const keyword = input.value.trim().toLowerCase();

    // 输入时清空已选ID（因为用户在重新搜索）
    hiddenId.value = '';

    const options = list.querySelectorAll('.supplier-combo-option');
    let hasVisible = false;
    options.forEach(opt => {
        const name = (opt.textContent || '').toLowerCase();
        const match = !keyword || name.includes(keyword);
        opt.style.display = match ? '' : 'none';
        if (match) hasVisible = true;
    });

    list.classList.toggle('show', hasVisible || !keyword);
}

function showSupplierDropdown(input) {
    const combobox = input.closest('.supplier-combobox');
    const list = combobox.querySelector('.supplier-combo-list');
    // 显示所有选项
    list.querySelectorAll('.supplier-combo-option').forEach(opt => {
        opt.style.display = '';
    });
    list.classList.add('show');
}

function hideSupplierDropdown(input) {
    // 延迟隐藏，让 mousedown 事件先触发
    setTimeout(() => {
        const combobox = input.closest('.supplier-combobox');
        const list = combobox.querySelector('.supplier-combo-list');
        list.classList.remove('show');

        // 如果没有选中任何选项（hiddenId为空），恢复为之前的值
        const hiddenId = combobox.querySelector('.supplier-combo-id');
        const itemIndex = parseInt(combobox.dataset.item);
        const quoteIndex = parseInt(combobox.dataset.quote);
        const quote = inquiryItems[itemIndex]?.quotes[quoteIndex];
        if (quote && !hiddenId.value) {
            input.value = quote.supplier_name || '';
        }
    }, 200);
}

// ==================== 快速新建材料 ====================

function showQuickMaterialForm(itemIndex) {
    const form = document.getElementById('quickMaterialForm' + itemIndex);
    if (form) form.style.display = '';
}

function hideQuickMaterialForm(itemIndex) {
    const form = document.getElementById('quickMaterialForm' + itemIndex);
    if (form) form.style.display = 'none';
}

async function submitQuickMaterial(itemIndex) {
    const nameEl = document.getElementById('qmName' + itemIndex);
    const specEl = document.getElementById('qmSpec' + itemIndex);
    const unitEl = document.getElementById('qmUnit' + itemIndex);

    const materialName = (nameEl?.value || '').trim();
    if (!materialName) {
        showToast('请输入材料名称', 'warning');
        return;
    }
    const spec = (specEl?.value || '').trim();
    if (!spec) {
        showToast('请输入规格', 'warning');
        return;
    }
    const unit = (unitEl?.value || '').trim();
    if (!unit) {
        showToast('请输入单位', 'warning');
        return;
    }

    const projectId = document.getElementById('inquiryProject')?.value;
    if (!projectId) {
        showToast('请先选择所属项目', 'warning');
        return;
    }

    const body = {
        project_id: parseInt(projectId, 10),
        material_name: materialName,
        specification: spec,
        unit_name: unit,
        brand: '',
        detail_spec: '',
        is_national_standard: 0,
        tax_price: 0,
        tax_rate: 0.01,
        freight: 0,
        inventory_min: 0,
        inventory_max: 0
    };

    try {
        const res = await api('/api/materials', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            showToast('材料已创建');

            // 刷新材料缓存
            await loadAllMaterialsForSelect();

            // 更新当前 item 的材料选择
            const newMaterial = (allMaterialsCache.length > 0 ? allMaterialsCache : materials || [])
                .find(m => m?.id == data.id);
            if (newMaterial) {
                onMaterialSelect(itemIndex, newMaterial.id);
            }

            // 隐藏表单并清空
            hideQuickMaterialForm(itemIndex);
            if (nameEl) nameEl.value = '';
            if (specEl) specEl.value = '';
            if (unitEl) unitEl.value = '';
        } else {
            showToast(data.message || '创建失败', 'error');
        }
    } catch (e) {
        showToast('创建材料失败: ' + e.message, 'error');
    }
}

function selectSupplierOption(option, itemIndex, quoteIndex) {
    const combobox = option.closest('.supplier-combobox');
    const input = combobox.querySelector('.supplier-combo-input');
    const hiddenId = combobox.querySelector('.supplier-combo-id');
    const supplierId = option.dataset.id;
    const supplierName = option.textContent;

    input.value = supplierName;
    hiddenId.value = supplierId;

    // 更新 inquiryItems 数据
    const quote = inquiryItems[itemIndex]?.quotes[quoteIndex];
    if (quote) {
        quote.supplier_id = supplierId;
        quote.supplier_name = supplierName;
        updateLowestFlag(itemIndex);
        updateInquiryTotal();
    }

    // 超过5个材料时，修改第一个材料的供应商同步到其他材料
    if (inquiryItems.length > 5 && itemIndex === 0) {
        for (let i = 1; i < inquiryItems.length; i++) {
            const targetQuote = inquiryItems[i]?.quotes[quoteIndex];
            if (targetQuote) {
                targetQuote.supplier_id = supplierId;
                targetQuote.supplier_name = supplierName;
            }
            // 更新对应DOM
            const targetRow = document.querySelector(`.supplier-combobox[data-item="${i}"][data-quote="${quoteIndex}"]`);
            if (targetRow) {
                const targetInput = targetRow.querySelector('.supplier-combo-input');
                const targetHiddenId = targetRow.querySelector('.supplier-combo-id');
                if (targetInput) targetInput.value = supplierName;
                if (targetHiddenId) targetHiddenId.value = supplierId;
            }
            updateLowestFlag(i);
        }
    }
}

function toggleSupplierDropdown(input) {
    const combobox = input.closest('.supplier-combobox');
    const list = combobox.querySelector('.supplier-combo-list');
    if (list.classList.contains('show')) {
        list.classList.remove('show');
    } else {
        list.querySelectorAll('.supplier-combo-option').forEach(opt => {
            opt.style.display = '';
        });
        list.classList.add('show');
        input.focus();
    }
}

function renderInquiryItems() {
    const container = document.getElementById('inquiryItemsContainer');
    if (!container) return;

    const validMaterials = (allMaterialsCache.length > 0 ? allMaterialsCache : materials) || [];
    const validSuppliers = suppliers || [];

    if (inquiryItems.length === 0) {
        container.innerHTML = '<div class="empty-hint">请添加询价材料</div>';
        return;
    }

    container.innerHTML = inquiryItems.map((item, itemIndex) => `
        <div class="inquiry-item-card">
            <div class="item-header">
                <div class="item-info">
                    <div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;">
                        <div class="material-picker" data-item="${itemIndex}" style="flex:1;min-width:220px;position:relative;">
                            <input type="text" class="material-picker-input"
                                   value="${escapeHtml(item.material_code || '')} ${escapeHtml(item.material_name || '')}${item.specification ? ' ' + escapeHtml(item.specification) : ''}"
                                   placeholder="点击选择材料..."
                                   onfocus="openMaterialPicker(this, ${itemIndex})"
                                   autocomplete="off" readonly
                                   style="width:100%;padding:6px 28px 6px 8px;border:1px solid var(--border-light);border-radius:4px;font-size:13px;cursor:pointer;background:#fff;">
                            <span style="position:absolute;right:8px;top:50%;transform:translateY(-50%);pointer-events:none;color:#999;">&#9662;</span>
                            <input type="hidden" class="material-picker-id" value="${item.material_id || ''}">
                        </div>
                        <button type="button" class="btn btn-sm" style="padding:4px 8px;font-size:11px;background:#e8f5e9;color:#2e7d32;border:1px solid #a5d6a7;border-radius:4px;cursor:pointer;white-space:nowrap;" onclick="showQuickMaterialForm(${itemIndex})">＋新建</button>
                    </div>
                    <!-- 快速新建材料表单（默认隐藏） -->
                    <div class="quick-material-form" id="quickMaterialForm${itemIndex}" style="display:none;margin-top:6px;padding:8px 10px;background:#f1f8e9;border:1px dashed #a5d6a7;border-radius:6px;">
                        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:flex-end;">
                            <div style="flex:1;min-width:80px;">
                                <label style="font-size:11px;color:#666;display:block;">名称 *</label>
                                <input type="text" id="qmName${itemIndex}" placeholder="材料名称" style="width:100%;padding:4px 6px;border:1px solid #ccc;border-radius:3px;font-size:12px;">
                            </div>
                            <div style="flex:1;min-width:60px;">
                                <label style="font-size:11px;color:#666;display:block;">规格 *</label>
                                <input type="text" id="qmSpec${itemIndex}" placeholder="规格" style="width:100%;padding:4px 6px;border:1px solid #ccc;border-radius:3px;font-size:12px;">
                            </div>
                            <div style="width:60px;">
                                <label style="font-size:11px;color:#666;display:block;">单位 *</label>
                                <input type="text" id="qmUnit${itemIndex}" placeholder="个" style="width:100%;padding:4px 6px;border:1px solid #ccc;border-radius:3px;font-size:12px;">
                            </div>
                            <button type="button" class="btn btn-primary btn-sm" style="padding:5px 10px;font-size:11px;" onclick="submitQuickMaterial(${itemIndex})">确定</button>
                            <button type="button" class="btn btn-secondary btn-sm" style="padding:5px 8px;font-size:11px;" onclick="hideQuickMaterialForm(${itemIndex})">取消</button>
                        </div>
                    </div>
                    ${item.specification ? `<span class="material-spec">${escapeHtml(item.specification)}</span>` : ''}
                    ${item.unit_name ? `<span class="unit">单位: ${escapeHtml(item.unit_name)}</span>` : ''}
                    <span class="library-price-badge">库内价: 含税 ¥${(item.tax_price || 0).toFixed(2)} / 现金含税 ¥${(item.cash_price || 0).toFixed(2)}</span>
                </div>
                <div class="item-quantity">
                    <label>采购数量:</label>
                    <input type="number" step="1" class="qty-input" value="${item.quantity}"
                           onchange="updateItemQuantity(${itemIndex}, this.value)">
                </div>
                <button type="button" class="btn btn-danger btn-sm" onclick="removeInquiryItem(${itemIndex})">删除材料</button>
            </div>
            <div style="display:flex;gap:10px;padding:8px 15px;background:#fafafa;border-bottom:1px solid var(--border);">
                <div style="flex:1;">
                    <label style="font-size:12px;color:#666;">详细规格 <span style="color:red;">*</span></label>
                    <input type="text" value="${escapeHtml(item.detail_spec || '')}"
                           onchange="updateItemField(${itemIndex}, 'detail_spec', this.value)"
                           placeholder="如：自喷漆800毫升/瓶" style="width:100%;padding:6px 8px;border:1px solid var(--border-light);border-radius:4px;font-size:13px;">
                </div>
                <div style="flex:0.6;">
                    <label style="font-size:12px;color:#666;">是否国标 <span style="color:red;">*</span></label>
                    <select onchange="updateItemField(${itemIndex}, 'is_national_standard', this.value === '' ? null : parseInt(this.value))"
                            style="width:100%;padding:6px 8px;border:1px solid var(--border-light);border-radius:4px;font-size:13px;" required>
                        <option value="">--请选择--</option>
                        <option value="0" ${item.is_national_standard === 0 ? 'selected' : ''}>否</option>
                        <option value="1" ${item.is_national_standard === 1 ? 'selected' : ''}>是</option>
                    </select>
                </div>
                <div style="flex:0.6;">
                    <label style="font-size:12px;color:#666;">是否现金含税价 <span style="color:red;">*</span></label>
                    <select onchange="onInquiryCashPriceChange(${itemIndex}, this.value === '' ? null : parseInt(this.value))"
                            style="width:100%;padding:6px 8px;border:1px solid var(--border-light);border-radius:4px;font-size:13px;" required>
                        <option value="0" ${item.is_cash_price === 0 ? 'selected' : ''}>否</option>
                        <option value="1" ${item.is_cash_price === 1 ? 'selected' : ''}>是</option>
                    </select>
                </div>
                <div style="flex:1;">
                    <label style="font-size:12px;color:#666;">品牌 <span style="color:red;">*</span></label>
                    <input type="text" value="${escapeHtml(item.brand || '')}"
                           onchange="updateItemField(${itemIndex}, 'brand', this.value)"
                           placeholder="请输入品牌" style="width:100%;padding:6px 8px;border:1px solid var(--border-light);border-radius:4px;font-size:13px;">
                </div>
            </div>

            <div class="quotes-grid">
                ${item.quotes.map((quote, quoteIndex) => `
                    <div class="quote-row ${quote.is_lowest ? 'lowest' : ''} ${quote.is_selected ? 'selected' : ''}" data-item="${itemIndex}" data-quote="${quoteIndex}">
                        ${quote.is_lowest ? '<div class="lowest-badge">最低价</div>' : ''}

                        <div class="quote-supplier">
                            <label>供应商</label>
                            <div class="supplier-combobox" data-item="${itemIndex}" data-quote="${quoteIndex}">
                                <input type="text" class="supplier-combo-input"
                                       value="${escapeHtml(quote.supplier_name || '')}"
                                       placeholder="输入搜索或下拉选择"
                                       oninput="filterSupplierDropdown(this, ${itemIndex}, ${quoteIndex})"
                                       onfocus="showSupplierDropdown(this)"
                                       onblur="hideSupplierDropdown(this)"
                                       autocomplete="off">
                                <input type="hidden" class="supplier-combo-id" value="${quote.supplier_id || ''}">
                                <span class="supplier-combo-arrow" onmousedown="toggleSupplierDropdown(this.previousElementSibling.previousElementSibling)">&#9662;</span>
                                <div class="supplier-combo-list">
                                    ${validSuppliers.map(s => `<div class="supplier-combo-option" data-id="${s?.id}" onmousedown="selectSupplierOption(this, ${itemIndex}, ${quoteIndex})">${escapeHtml(s?.supplier_name || '')}</div>`).join('')}
                                </div>
                            </div>
                        </div>

                        <div class="quote-inputs">
                            <div class="input-group">
                                <label>${item.is_cash_price ? '现金含税价' : '含税单价'}</label>
                                <input type="number" step="0.01" value="${quote.tax_price || ''}"
                                       oninput="updateQuoteFieldLive(${itemIndex}, ${quoteIndex}, this.value)"
                                       onchange="updateQuoteField(${itemIndex}, ${quoteIndex}, 'tax_price', this.value)"
                                       placeholder="0.00">
                                ${(() => {
                                    if (!(quote.tax_price > 0)) return '<span class="price-diff-hint"></span>';
                                    const diff = parseFloat(quote.tax_price) - parseFloat(item.library_price || 0);
                                    const pct = item.library_price > 0 ? ((diff / item.library_price) * 100).toFixed(1) : '';
                                    const color = diff < 0 ? 'var(--success)' : diff > 0 ? 'var(--danger)' : 'var(--text-muted)';
                                    const arrow = diff < 0 ? '↓' : diff > 0 ? '↑' : '=';
                                    return `<span class="price-diff-hint" style="color:${color};">比库内价 ${arrow} ¥${Math.abs(diff).toFixed(2)}${pct ? ' (' + pct + '%)' : ''}</span>`;
                                })()}
                            </div>
                            <div class="input-group">
                                <label>税率</label>
                                <select onchange="updateQuoteField(${itemIndex}, ${quoteIndex}, 'tax_rate', this.value)">
                                    <option value="0.01" ${quote.tax_rate == 0.01 ? 'selected' : ''}>1%</option>
                                    <option value="0.03" ${quote.tax_rate == 0.03 ? 'selected' : ''}>3%</option>
                                    <option value="0.06" ${quote.tax_rate == 0.06 ? 'selected' : ''}>6%</option>
                                    <option value="0.09" ${quote.tax_rate == 0.09 ? 'selected' : ''}>9%</option>
                                    <option value="0.13" ${quote.tax_rate == 0.13 ? 'selected' : ''}>13%</option>
                                </select>
                            </div>
                            <div class="input-group">
                                <label>不含税单价</label>
                                 <input type="number" step="0.01" value="${quote.tax_exempt_price ? quote.tax_exempt_price.toFixed(2) : ''}"
                                        class="quote-tax-exempt"
                                        placeholder="0.00" readonly>
                            </div>
                            <div class="input-group">
                                <label>报价金额</label>
                                <input type="text" value="¥${(quote.total_amount || 0).toFixed(2)}" readonly
                                       class="quote-total-amount"
                                       style="border:1px solid var(--border-light);border-radius:var(--radius-sm);padding:6px 8px;font-size:13px;height:34px;box-sizing:border-box;background:#f9f9f9;font-weight:bold;color:var(--danger);">
                            </div>
                        </div>

                        <div class="quote-actions">
                            <button type="button" class="btn quote-select-btn ${quote.is_selected ? 'btn-primary' : 'btn-outline'}"
                                    onclick="selectQuote(${itemIndex}, ${quoteIndex})">
                                ${quote.is_selected ? '已选定' : '设为拟定'}
                            </button>
                            ${item.quotes.length > 1 ? `<button type="button" class="btn btn-danger btn-sm quote-remove-btn" onclick="event.stopPropagation();removeQuoteFromItem(${itemIndex}, ${quoteIndex})" title="删除此供应商报价">&times;</button>` : ''}
                        </div>
                    </div>
                `).join('')}
                <button type="button" class="add-quote-btn" onclick="addQuoteToItem(${itemIndex})">+ 添加供应商报价</button>
            </div>
        </div>
    `).join('');
}

function updateInquiryTotal() {
    let total = 0;
    (inquiryItems || []).forEach(item => {
        (item.quotes || []).forEach(quote => {
            if (quote.is_selected && quote.tax_price > 0) {
                total += (quote.tax_price || 0) * (item.quantity || 1);
            }
        });
    });

    const el = document.getElementById('inquiryTotal');
    if (el) el.textContent = total.toFixed(2);
}

// 供勾选功能调用的入口：接收预构建好的 items 数组，直接打开询价弹窗
function openInquiryWithItems(items) {
    if (!items || items.length === 0) {
        showToast('没有可生成的材料', 'info');
        return;
    }

    closeCartDrawer();

    const modal = document.getElementById('modal-inquiry');
    if (modal) modal.dataset.loaded = 'true';

    document.getElementById('inquiryDate').value = new Date().toISOString().split('T')[0];

    // 先确保供应商数据已加载，再构建默认报价（防止供应商未加载导致不显示）
    const _buildItems = () => {
        inquiryItems = items.map(item => ({
            material_id: item.material_id,
            material_name: item.material_name || '',
            material_code: item.material_code || '',
            specification: item.specification || '',
            detail_spec: item.detail_spec || '',
            brand: item.brand || '',
            unit_name: item.unit_name || '',
            quantity: parseFloat(item.quantity || 1),
            library_price: item.library_price || item.tax_price || 0,
            tax_price: item.tax_price || 0,
            tax_exempt_price: item.tax_exempt_price || 0,
            cash_price: item.cash_price || 0,
            cash_tax_price: item.cash_tax_price || 0,
            tax_rate: item.tax_rate || 0.01,
            is_national_standard: item.is_national_standard || 0,
            is_cash_price: item.is_cash_price || 0,
            selected_quote_id: null,
            quotes: buildDefaultQuotes()
        }));
        renderInquiryItems();
        updateInquiryTotal();
    };

    modal.classList.add('show');
    _buildItems();

    // 后台加载供应商和材料缓存；不阻塞弹窗生成体验。
    Promise.all([
        suppliers.length === 0 ? loadUnitsAndSuppliers() : Promise.resolve(),
        allMaterialsCache.length === 0 ? loadAllMaterialsForSelect() : Promise.resolve()
    ]).then(() => {
        console.log('后台数据加载完成：供应商', suppliers.length, '材料缓存', allMaterialsCache.length);
        const defaultQuotes = buildDefaultQuotes();
        inquiryItems.forEach(item => {
            if (!item.quotes) return;
            item.quotes.forEach((q, qi) => {
                if (!q.supplier_id && defaultQuotes[qi]) {
                    q.supplier_id = defaultQuotes[qi].supplier_id;
                    q.supplier_name = defaultQuotes[qi].supplier_name;
                    q.tax_rate = defaultQuotes[qi].tax_rate;
                }
            });
        });
        renderInquiryItems();
    }).catch((e) => {
        console.warn('后台数据加载失败，已使用当前缓存生成询价单:', e);
    });

    loadProjectsToInquirySelect();

    // 生成成功后清空勾选
    clearSelection();
}

// 重写购物车生成询价单的逻辑（适配新结构）
let _generatingFromCart = false;
async function generateInquiryFromCart() {
    if (_generatingFromCart) return;
    const rawCart = cartItems || [];
    const validCart = rawCart.filter(item => item != null && item != undefined);
    if (validCart.length === 0) {
        showToast('购物车为空', 'info');
        return;
    }
    _generatingFromCart = true;

    console.log('=== generateInquiryFromCart START ===');
    console.log('validCart count:', validCart.length);

    closeCartDrawer();

    // 先标记modal已加载，防止openModal重复触发初始化逻辑
    const modal = document.getElementById('modal-inquiry');
    if (modal) modal.dataset.loaded = 'true';

    // 设置默认日期
    document.getElementById('inquiryDate').value = new Date().toISOString().split('T')[0];

    // 先用购物车已有数据立即构建 inquiryItems 并显示模态框（不等待网络）
    inquiryItems = validCart.map(item => {
        const materialId = parseInt(item?.material_id || item?.['商品编号'], 10) || '';
        // 先从缓存查，缓存没有就用购物车自带数据
        const m = allMaterialsCache.length > 0
            ? allMaterialsCache.find(x => x?.id == materialId)
            : null;
        return {
            material_id: materialId,
            material_name: m?.material_name || item?.material_name || item?.['商品名称'] || '',
            material_code: m?.material_code || item?.material_code || item?.['商品编码'] || '',
            specification: m?.specification || item?.specification || '',
            detail_spec: m?.detail_spec || item?.detail_spec || '',
            brand: m?.brand || item?.brand || '',
            unit_name: m?.unit_name || item?.unit_name || '',
            quantity: parseFloat(item?.quantity || 1),
            library_price: m?.tax_price || item?.library_price || 0,
            tax_price: m?.tax_price || item?.library_price || 0,
            cash_price: m?.cash_price || item?.cash_price || 0,
            selected_quote_id: null,
            is_national_standard: 0,
            is_cash_price: 0,
            quotes: buildDefaultQuotes()
        };
    });

    // 立即显示模态框
    modal.classList.add('show');
    renderInquiryItems();
    updateInquiryTotal();

    // 后台异步加载供应商和材料缓存（不阻塞界面）
    // 加载完成后重新填充默认供应商（防止供应商未加载时显示为空）
    Promise.all([
        suppliers.length === 0 ? loadUnitsAndSuppliers() : Promise.resolve(),
        allMaterialsCache.length === 0 ? loadAllMaterialsForSelect() : Promise.resolve()
    ]).then(() => {
        console.log('后台数据加载完成：供应商', suppliers.length, '材料缓存', allMaterialsCache.length);
        // 供应商加载完成后，为没有供应商的 quote 重新填充默认供应商
        const defaultQuotes = buildDefaultQuotes();
        inquiryItems.forEach(item => {
            if (item.quotes) {
                item.quotes.forEach((q, qi) => {
                    if (!q.supplier_id && defaultQuotes[qi]) {
                        q.supplier_id = defaultQuotes[qi].supplier_id;
                        q.supplier_name = defaultQuotes[qi].supplier_name;
                    }
                });
            }
        });
        renderInquiryItems();
    });

    // 项目列表异步加载
    loadProjectsToInquirySelect();

    console.log('=== generateInquiryFromCart END ===');
    console.log('inquiryItems:', JSON.stringify(inquiryItems, null, 2));
    _generatingFromCart = false;
}

async function submitInquiryForm() {
    // 校验项目必填
    const projectId = document.getElementById('inquiryProject')?.value;
    if (!projectId) {
        showToast('请选择所属项目', 'warning');
        return;
    }

    // 深拷贝 inquiryItems 避免修改原始数据
    const rawItems = (inquiryItems || []).filter(item => item && item.material_id);

    if (rawItems.length === 0) {
        showToast('请添加有效的询价材料（需选择材料）', 'warning');
        return;
    }

    // 校验详细规格、品牌、是否国标、是否现金含税价必填
    for (let i = 0; i < rawItems.length; i++) {
        const item = rawItems[i];
        if (!item.detail_spec || !item.detail_spec.trim()) {
            showToast(`第 ${i + 1} 个材料的"详细规格"不能为空，请填写后重新提交`, 'warning');
            return;
        }
        if (!item.brand || !item.brand.trim()) {
            showToast(`第 ${i + 1} 个材料的"品牌"不能为空，请填写后重新提交`, 'warning');
            return;
        }
        if (item.is_national_standard === null || item.is_national_standard === undefined) {
            showToast(`第 ${i + 1} 个材料的"是否国标"不能为空，请选择后重新提交`, 'warning');
            return;
        }
        if (item.is_cash_price === null || item.is_cash_price === undefined) {
            showToast(`第 ${i + 1} 个材料的"是否现金含税价"不能为空，请选择后重新提交`, 'warning');
            return;
        }
    }

    // 先将详细规格和品牌更新到材料信息表
    const currentUser = JSON.parse(sessionStorage.getItem('currentUser') || '{}');
    const selectedOption = document.getElementById('inquiryProject')?.selectedOptions?.[0];
    const inquiryProjectCode = selectedOption?.getAttribute('data-code') || '';
    const inquiryPrefix = inquiryProjectCode.substring(0, 2).toUpperCase();
    try {
        for (const item of rawItems) {
            const m = (allMaterialsCache.length > 0 ? allMaterialsCache : materials || []).find(x => x?.id == item.material_id);
            if (m) {
                // liuruitao 跨区域询价时，不覆盖原始材料的详细规格和品牌
                const matPrefix = (m.material_code || '').substring(0, 2).toUpperCase();
                const isCrossRegion = matPrefix !== inquiryPrefix && inquiryPrefix;
                const isLiuruitaoCrossRegion = currentUser.username === 'liuruitao' && isCrossRegion;
                const updateBody = {
                    material_name: m.material_name,
                    specification: m.specification,
                    detail_spec: isLiuruitaoCrossRegion ? (m.detail_spec || '') : item.detail_spec.trim(),
                    is_national_standard: m.is_national_standard || 0,
                    brand: isLiuruitaoCrossRegion ? (m.brand || '') : item.brand.trim(),
                    unit_name: m.unit_name || '',
                    tax_price: m.tax_price || 0,
                    tax_rate: m.tax_rate || 0.01,
                    is_cash_price: m.is_cash_price || 0,
                    cash_price: m.cash_price || 0,
                    default_supplier_id: m.default_supplier_id || null,
                    remark: m.remark || ''
                };
                await api(`/api/materials/${item.material_id}`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(updateBody)
                });
            }
        }
    } catch (e) {
        console.error('更新材料信息失败:', e);
        showToast('更新材料详细规格/品牌失败: ' + e.message, 'error');
        return;
    }

    // 构建请求数据，确保类型正确
    const items = rawItems.map(item => {
        const quotes = (item.quotes || [])
            .filter(q => q.supplier_id && parseFloat(q.tax_price) > 0)
            .map(q => ({
                supplier_id: parseInt(q.supplier_id, 10),
                tax_price: parseFloat(q.tax_price) || 0,
                tax_exempt_price: parseFloat(q.tax_exempt_price) || 0,
                tax_rate: parseFloat(q.tax_rate) || 0.13
            }));

        return {
            material_id: parseInt(item.material_id, 10),
            quantity: parseFloat(item.quantity) || 1,
            library_price: parseFloat(item.library_price) || 0,
            selected_quote_id: item.selected_quote_id ? parseInt(item.selected_quote_id, 10) : null,
            is_national_standard: item.is_national_standard !== null && item.is_national_standard !== undefined ? item.is_national_standard : 0,
            is_cash_price: item.is_cash_price !== null && item.is_cash_price !== undefined ? item.is_cash_price : 0,
            detail_spec: (item.detail_spec || '').trim(),
            brand: (item.brand || '').trim(),
            quotes: quotes
        };
    }).filter(item => !isNaN(item.material_id) && item.material_id > 0);

    if (items.length === 0) {
        showToast('请添加有效的询价材料（材料ID无效）', 'warning');
        return;
    }

    // 检查是否有至少一条有效报价
    const hasAnyQuote = items.some(item => item.quotes.length > 0);
    if (!hasAnyQuote) {
        showToast('请至少为一种材料填写供应商报价', 'warning');
        return;
    }

    const requestData = {
        inquiry_date: document.getElementById('inquiryDate')?.value || '',
        project_id: document.getElementById('inquiryProject')?.value || null,
        remark: document.getElementById('inquiryRemark')?.value || '',
        items: items
    };

    console.log('Sending requestData:', JSON.stringify(requestData));

    try {
        let res;
        if (editingInquiryId) {
            // 编辑模式：PUT 更新已有询价单并重新提交
            res = await api(`/api/purchase-inquiries/${editingInquiryId}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(requestData)
            });
        } else {
            // 新建模式
            res = await api('/api/purchase-inquiries', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(requestData)
            });
        }
        const data = await res.json();
        console.log('Response data:', data);
        if (data.success) {
            showToast(editingInquiryId ? '询价单已重新提交！' : `询价单创建成功！\n单号: ${data.inquiry_no}`, { credentials: 'same-origin' });
            closeModal('modal-inquiry');
            inquiryItems = [];
            editingInquiryId = null;
            // 清空购物车并保存到本地存储
            cartItems = [];
            saveCartToStorage();
            updateCartBadge();
            // 重置标题
            const modal = document.getElementById('modal-inquiry');
            if (modal) modal.querySelector('.modal-header h2').textContent = '新建询价单';
            loadInquiries();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        console.error('Fetch error:', e);
        showToast(editingInquiryId ? '重新提交失败: ' + e.message : '创建失败: ' + e.message, 'error');
    }
}

// ==================== 草稿（暂存）功能 ====================

async function saveInquiryDraft() {
    // 深拷贝 inquiryItems
    const rawItems = (inquiryItems || []).map(item => {
        if (!item) return null;
        const quotes = (item.quotes || []).map(q => ({
            supplier_id: q.supplier_id ? parseInt(q.supplier_id, 10) : null,
            tax_price: parseFloat(q.tax_price) || 0,
            tax_exempt_price: parseFloat(q.tax_exempt_price) || 0,
            tax_rate: parseFloat(q.tax_rate) || 0.13
        }));

        return {
            material_id: item.material_id ? parseInt(item.material_id, 10) : null,
            quantity: parseFloat(item.quantity) || 1,
            library_price: parseFloat(item.library_price) || 0,
            selected_quote_id: item.selected_quote_id ? parseInt(item.selected_quote_id, 10) : null,
            is_national_standard: item.is_national_standard !== null && item.is_national_standard !== undefined ? item.is_national_standard : 0,
            is_cash_price: item.is_cash_price !== null && item.is_cash_price !== undefined ? item.is_cash_price : 0,
            detail_spec: (item.detail_spec || '').trim(),
            brand: (item.brand || '').trim(),
            quotes: quotes
        };
    }).filter(item => item !== null);

    const requestData = {
        draft_id: editingInquiryId || null,
        inquiry_date: document.getElementById('inquiryDate')?.value || '',
        project_id: document.getElementById('inquiryProject')?.value || null,
        remark: document.getElementById('inquiryRemark')?.value || '',
        items: rawItems
    };

    try {
        const res = await api('/api/purchase-inquiries/draft', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(requestData)
        });
        const data = await res.json();
        if (data.success) {
            // 更新 editingInquiryId 以便后续暂存覆盖同一草稿
            editingInquiryId = data.draft_id;
            // 更新标题
            const modal = document.getElementById('modal-inquiry');
            if (modal) modal.querySelector('.modal-header h2').textContent = `编辑询价单 - ${data.inquiry_no}`;
            showToast('草稿已保存！');
            // 刷新草稿列表
            loadInquiryDrafts();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        console.error('保存草稿失败:', e);
        showToast('保存草稿失败: ' + e.message, 'error');
    }
}

async function loadInquiryDrafts() {
    try {
        const res = await api('/api/purchase-inquiries/drafts');
        const data = await res.json();
        if (data.success) {
            renderDraftsTable(data.data);
        }
    } catch (e) {
        console.error('加载草稿失败:', e);
    }
}

function renderDraftsTable(drafts) {
    const section = document.getElementById('draftsSection');
    const tbody = document.getElementById('draftsTable');
    const countEl = document.getElementById('draftsCount');

    if (!drafts || drafts.length === 0) {
        section.style.display = 'none';
        return;
    }

    section.style.display = '';
    countEl.textContent = `(${drafts.length} 条)`;

    tbody.innerHTML = drafts.map(d => `
        <tr>
            <td>${d.inquiry_no}</td>
            <td>${d.inquiry_date || '-'}</td>
            <td>${d.remark || '-'}</td>
            <td style="white-space:nowrap;">
                <button class="btn btn-success" style="padding:4px 8px;font-size:12px;" onclick="editInquiry(${d.id})">继续编辑</button>
                <button class="btn btn-secondary" style="padding:4px 8px;font-size:12px;" onclick="exportDraftQuoteSheet(${d.id})">导出询价表</button>
                <button class="btn btn-danger" style="padding:4px 8px;font-size:12px;" onclick="deleteInquiryDraft(${d.id})">删除</button>
            </td>
        </tr>
    `).join('');
}

function exportDraftQuoteSheet(id) {
    window.location.href = `/api/purchase-inquiries/draft/${id}/export-quote-sheet`;
}

async function deleteInquiryDraft(id) {
    if (!confirm('确定要删除此草稿吗？此操作不可恢复！')) return;

    try {
        const res = await api(`/api/purchase-inquiries/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            showToast('草稿已删除');
            loadInquiryDrafts();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('删除失败: ' + e.message, 'error');
    }
}

// ==================== 入库单明细操作 ====================

// ==================== 入库单明细操作 ====================

async function openStockInModal() {
    await Promise.all([loadUnitsAndSuppliers(), loadWarehouses()]);
    openModal('modal-stock-in');
}

function addStockInDetail() {
    stockInDetails.push({
        material_id: '',
        unit_price: 0,
        quantity: 1
    });
    renderStockInDetails();
}

function renderStockInDetails() {
    const tbody = document.getElementById('stockInDetails');
    tbody.innerHTML = stockInDetails.map((d, i) => `
        <tr>
            <td>
                <select onchange="updateStockInDetail(${i}, 'material_id', this.value)">
                    <option value="">--请选择--</option>
                    ${(allMaterialsCache.length > 0 ? allMaterialsCache : materials).map(m => `<option value="${m.id}" ${d.material_id == m.id ? 'selected' : ''}>${m.material_code} - ${m.material_name}</option>`).join('')}
                </select>
            </td>
            <td><input type="number" step="0.01" value="${d.unit_price}" onchange="updateStockInDetail(${i}, 'unit_price', this.value)"></td>
            <td><input type="number" step="0.01" value="${d.quantity}" onchange="updateStockInDetail(${i}, 'quantity', this.value)"></td>
            <td>¥${((d.unit_price || 0) * (d.quantity || 0)).toFixed(2)}</td>
            <td><button class="btn btn-danger" onclick="removeStockInDetail(${i})">删除</button></td>
        </tr>
    `).join('');
}

function updateStockInDetail(index, field, value) {
    if (field === 'material_id') {
        const m = (allMaterialsCache.length > 0 ? allMaterialsCache : materials).find(x => x.id == value);
        stockInDetails[index].material_id = value;
        stockInDetails[index].unit_price = m ? m.tax_price : 0;
    } else {
        stockInDetails[index][field] = parseFloat(value) || 0;
    }
    renderStockInDetails();
}

function removeStockInDetail(index) {
    stockInDetails.splice(index, 1);
    renderStockInDetails();
}

document.getElementById('stockInForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const validDetails = stockInDetails.filter(d => d.material_id && d.unit_price > 0);
    if (validDetails.length === 0) {
        showToast('请添加有效的入库明细', 'warning');
        return;
    }

    const body = {
        source_type: document.getElementById('stockInType').value,
        supplier_id: document.getElementById('stockInSupplier').value || null,
        remark: document.getElementById('stockInRemark').value,
        details: validDetails.map(d => ({
            material_id: parseInt(d.material_id),
            unit_price: parseFloat(d.unit_price),
            quantity: parseFloat(d.quantity) || 1
        }))
    };

    try {
        const res = await api('/api/stock-in', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            showToast(`入库单创建成功！\n单号: ${data.order_no}`, { credentials: 'same-origin' });
            closeModal('modal-stock-in');
            stockInDetails = [];
            loadStockIn();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('创建失败', 'error');
    }
});

// ==================== 模态框控制 ====================

function openModal(id) {
    const modal = document.getElementById(id);
    modal.classList.add('show');

    // 打开询价单模态框时加载数据
    if (id === 'modal-inquiry') {
        // 如果是新建（非编辑草稿），重置表单
        if (!editingInquiryId) {
            inquiryItems = [];
            document.getElementById('inquiryDate').value = new Date().toISOString().split('T')[0];
            document.getElementById('inquiryRemark').value = '';
            document.getElementById('inquiryProject').value = '';
            modal.querySelector('.modal-header h2').textContent = '新建询价单';
        }
        if (!modal.dataset.loaded) {
            modal.dataset.loaded = 'true';
        }
        loadProjectsToInquirySelect();
        Promise.all([loadUnitsAndSuppliers(), loadAllMaterialsForSelect()]).then(() => {
            if (inquiryItems.length === 0) {
                addInquiryItem();
            }
            renderInquiryItems();
        });
    }
    // 打开入库单模态框时加载数据
    if (id === 'modal-stock-in' && !modal.dataset.loaded) {
        Promise.all([loadUnitsAndSuppliers(), loadAllMaterialsForSelect(), loadWarehouses()]);
        modal.dataset.loaded = 'true';
    }
    // 打开对账单模态框时初始化
    if (id === 'modal-reconciliation') {
        initReconForm();
    }
}

function closeModal(id) {
    document.getElementById(id).classList.remove('show');
    // 关闭询价单模态框时重置编辑状态
    if (id === 'modal-inquiry') {
        editingInquiryId = null;
        document.querySelector('#modal-inquiry .modal-header h2').textContent = '新建询价单';
    }
}


// ==================== 系统设置 ====================

let allUsers = [];
let allRoles = [];

async function loadUsers() {
    try {
        const [usersRes, rolesCached] = await Promise.all([
            api('/api/users'),
            loadCacheOrFetch('dict_roles', '/api/roles')
        ]);
        const usersData = await usersRes.json();
        const rolesData = rolesCached;

        allUsers = usersData.success ? usersData.data : [];
        allRoles = rolesData.success ? rolesData.data : [];

        renderUserTable();
    } catch (e) {
        showToast('加载用户失败', 'error');
    }
}

function renderUserTable() {
    const tbody = document.getElementById('userTable');
    tbody.innerHTML = allUsers.map(u => {
        const projects = u.projects || [];
        const projectTags = projects.length > 0
            ? projects.map(p =>
                `<span style="display:inline-block;font-size:11px;background:var(--primary-light);color:var(--primary);padding:2px 8px;border-radius:10px;margin:2px;">${escapeHtml(p.project_name)}</span>`
            ).join('')
            : '<span style="color:#999;">未绑定</span>';
        return `
        <tr>
            <td>${u.id}</td>
            <td>${u.username}</td>
            <td>${u.real_name}</td>
            <td>${u.role_name || '-'}</td>
            <td style="max-width:300px;overflow:hidden;">${projectTags}</td>
            <td><span class="status ${u.is_active ? 'approved' : 'rejected'}">${u.is_active ? '启用' : '禁用'}</span></td>
            <td>
                <button class="btn btn-secondary" onclick="editUser(${u.id})">编辑</button>
                ${u.id !== 1 ? `<button class="btn btn-danger" onclick="deleteUser(${u.id})">删除</button>` : ''}
            </td>
        </tr>`;
    }).join('');
}

async function editUser(id) {
    const u = allUsers.find(x => x.id === id);
    if (!u) return;

    await loadRolesToSelect();
    await loadProjectsToCheckboxes(u.projects || []);

    document.getElementById('userId').value = u.id;
    document.getElementById('userUsername').value = u.username;
    document.getElementById('userRealName').value = u.real_name;
    document.getElementById('userPassword').value = '';
    document.getElementById('userPassword').placeholder = '留空则不修改';
    document.getElementById('userRole').value = u.role_id || '';
    document.getElementById('userActive').value = u.is_active ? '1' : '0';
    document.getElementById('userModalTitle').textContent = '编辑用户';

    openModal('modal-user');
}

async function deleteUser(id) {
    if (!confirm('确定要删除该用户吗？')) return;

    try {
        const res = await api(`/api/users/${id}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            showToast('删除成功', { credentials: 'same-origin' });
            loadUsers();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

async function loadRolesToSelect() {
    try {
        const res = await api('/api/roles');
        const data = await res.json();
        if (data.success) {
            const roleSelect = document.getElementById('userRole');
            roleSelect.innerHTML = data.data.map(r => `<option value="${r.id}">${r.role_name}</option>`).join('');
        }
    } catch (e) {}
}

async function loadProjectsToCheckboxes(selectedProjects = []) {
    try {
        const res = await api('/api/projects');
        const data = await res.json();
        const container = document.getElementById('userProjectsCheckboxes');
        if (!data.success || !data.data || data.data.length === 0) {
            container.innerHTML = '<span style="color:#999;font-size:13px;">暂无项目，请先在项目管理中创建</span>';
            return;
        }
        const selectedIds = selectedProjects.map(p => p.id);
        container.innerHTML = data.data.map(p => `
            <label style="display:flex;align-items:center;gap:4px;font-size:13px;cursor:pointer;white-space:nowrap;">
                <input type="checkbox" name="userProject" value="${p.id}" ${selectedIds.includes(p.id) ? 'checked' : ''}>
                ${escapeHtml(p.project_name)}
            </label>
        `).join('');
    } catch (e) {
        document.getElementById('userProjectsCheckboxes').innerHTML = '<span style="color:#999;">加载失败</span>';
    }
}

// 加载项目到询价单下拉（只加载当前用户绑定的项目，单个时自动选中）
async function loadProjectsToInquirySelect() {
    try {
        const res = await api('/api/projects?mine=1');
        const data = await res.json();
        const select = document.getElementById('inquiryProject');
        if (!select) return;
        select.innerHTML = '<option value="">--选择项目--</option>';
        const projects = data.data || [];
        projects.forEach(p => {
            select.innerHTML += `<option value="${p.id}" data-code="${p.project_code || ''}">${escapeHtml(p.project_name)}</option>`;
        });
        // 如果只有一个项目，自动选中
        if (projects.length === 1) {
            select.value = projects[0].id;
        }
    } catch(e) {
        console.error('加载项目失败:', e);
    }
}

function getSelectedProjectIds() {
    const checkboxes = document.querySelectorAll('input[name="userProject"]:checked');
    return Array.from(checkboxes).map(cb => parseInt(cb.value));
}

async function openNewUserModal() {
    document.getElementById('userId').value = '';
    document.getElementById('userUsername').value = '';
    document.getElementById('userRealName').value = '';
    document.getElementById('userPassword').value = '';
    document.getElementById('userPassword').placeholder = '默认密码: 888888';
    document.getElementById('userActive').value = '1';
    document.getElementById('userModalTitle').textContent = '新建用户';

    await loadRolesToSelect();
    await loadProjectsToCheckboxes([]);

    openModal('modal-user');
}

document.getElementById('userForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const id = document.getElementById('userId').value;
    const body = {
        username: document.getElementById('userUsername').value,
        real_name: document.getElementById('userRealName').value,
        role_id: document.getElementById('userRole').value || null,
        is_active: parseInt(document.getElementById('userActive').value),
        project_ids: getSelectedProjectIds()
    };

    const password = document.getElementById('userPassword').value;
    if (password) {
        body.password = password;
    }

    try {
        const url = id ? `/api/users/${id}` : '/api/users';
        const method = id ? 'PUT' : 'POST';
        const res = await api(url, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            showToast(id ? '更新成功' : '创建成功', { credentials: 'same-origin' });
            closeModal('modal-user');
            loadUsers();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('保存失败', 'error');
    }
});

// 覆写快捷按钮打开入库模态框
document.querySelectorAll('.shortcut-btn').forEach(btn => {
    const text = btn.querySelector('.text')?.textContent;
    if (text === '新建入库') {
        btn.onclick = () => openStockInModal();
    }
});

// ==================== 项目管理 ====================

let allProjects = [];

async function loadProjects() {
    try {
        const res = await api('/api/projects');
        const data = await res.json();
        if (data.success) {
            allProjects = data.data || [];
            renderProjectTable();
        }
    } catch (e) {
        console.error('加载项目失败', e);
    }
}

function renderProjectTable() {
    const tbody = document.getElementById('projectTable');
    if (!allProjects || allProjects.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:#999;">暂无项目，点击上方按钮新建</td></tr>';
        return;
    }

    tbody.innerHTML = allProjects.map(p => `
        <tr>
            <td><strong>${escapeHtml(p.project_code || '')}</strong></td>
            <td>${escapeHtml(p.project_name || '')}</td>
            <td>
                <button class="btn btn-secondary" onclick="editProject(${p.id})">编辑</button>
                <button class="btn btn-danger" onclick="deleteProject(${p.id})">删除</button>
            </td>
        </tr>
    `).join('');
}

async function openNewProjectModal() {
    document.getElementById('projectId').value = '';
    document.getElementById('projectCode').value = '';
    document.getElementById('projectName').value = '';
    document.getElementById('projectContract').value = '';
    document.getElementById('projectStartDate').value = '';
    document.getElementById('projectEndDate').value = '';
    document.getElementById('projectRemark').value = '';
    document.getElementById('projectModalTitle').textContent = '新建项目';

    // 加载客户下拉
    await loadCustomersToSelect();

    openModal('modal-project');
}

async function editProject(id) {
    const p = allProjects.find(x => x.id === id);
    if (!p) return;

    document.getElementById('projectId').value = p.id;
    document.getElementById('projectCode').value = p.project_code || '';
    document.getElementById('projectName').value = p.project_name || '';
    document.getElementById('projectContract').value = p.contract_no || '';
    document.getElementById('projectStartDate').value = p.start_date || '';
    document.getElementById('projectEndDate').value = p.end_date || '';
    document.getElementById('projectRemark').value = p.remark || '';
    document.getElementById('projectModalTitle').textContent = '编辑项目';

    await loadCustomersToSelect(p.customer_id);

    openModal('modal-project');
}

async function loadCustomersToSelect(selectedId = null) {
    try {
        const res = await api('/api/customers');
        const data = await res.json();
        const select = document.getElementById('projectCustomer');
        select.innerHTML = '<option value="">--选择客户--</option>';
        (data.data || []).forEach(c => {
            select.innerHTML += `<option value="${c.id}" ${selectedId && c.id === selectedId ? 'selected' : ''}>${escapeHtml(c.customer_name)}</option>`;
        });
    } catch (e) {
        console.error('加载客户失败', e);
    }
}

async function deleteProject(id) {
    if (!confirm('确定删除该项目？')) return;

    try {
        const res = await api(`/api/projects/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            loadProjects();
        } else {
            showToast(data.message || '删除失败', 'error');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

document.getElementById('projectForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('projectId').value;
    const body = {
        project_code: document.getElementById('projectCode').value.trim(),
        project_name: document.getElementById('projectName').value.trim(),
        contract_no: document.getElementById('projectContract').value.trim(),
        customer_id: parseInt(document.getElementById('projectCustomer').value) || null,
        start_date: document.getElementById('projectStartDate').value || null,
        end_date: document.getElementById('projectEndDate').value || null,
        remark: document.getElementById('projectRemark').value.trim()
    };

    if (!body.project_name) {
        showToast('项目名称不能为空', 'warning');
        return;
    }

    try {
        const url = id ? `/api/projects/${id}` : '/api/projects';
        const method = id ? 'PUT' : 'POST';
        const res = await api(url, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            showToast(id ? '项目更新成功' : '项目创建成功', { credentials: 'same-origin' });
            closeModal('modal-project');
            loadProjects();
        } else {
            showToast(data.message || '操作失败', 'error');
        }
    } catch (e) {
        console.error('项目保存失败:', e);
        showToast('保存失败，请检查网络连接', 'error');
    }
});

// ==================== 甲供材专项量控 ====================

let ownerSuppliedTab = 'controls';
let ownerSuppliedRecords = { controls: [], demands: [], transactions: [], issues: [] };
let ownerSuppliedModal = { type: 'controls', id: null };

const ownerSuppliedConfigs = {
    controls: {
        label: '量控台账',
        endpoint: 'controls',
        fields: [
            ['control_level', '管控等级', 'select', 'A类重点|B类常规|C类简化'],
            ['building', '单位工程/楼栋'], ['work_item', '分部分项工程'],
            ['material_name', '材料名称 *'], ['specification', '规格型号'], ['unit', '单位 *'],
            ['contract_quantity', '合同暂定量', 'number'], ['budget_quantity', '图纸预算量', 'number'],
            ['change_quantity', '变更调整量', 'number'], ['arrival_quantity', '累计到货量', 'number'],
            ['issued_quantity', '累计领用量', 'number'], ['theoretical_quantity', '理论耗用量', 'number'],
            ['site_surplus', '现场余料', 'number'], ['contractor_inventory', '施工单位库存', 'number'],
            ['transit_quantity', '在途量', 'number'], ['responsible_person', '责任人'],
            ['reason_measures', '原因及措施', 'textarea', '', 'wide'], ['remark', '备注', 'textarea', '', 'wide']
        ]
    },
    demands: {
        label: '月度需求',
        endpoint: 'demands',
        fields: [
            ['plan_month', '计划月份 *', 'month'], ['building', '单位工程/楼栋'], ['construction_area', '施工部位'],
            ['material_name', '材料名称 *'], ['specification', '规格型号'], ['unit', '单位 *'],
            ['planned_quantity', '计划需求量', 'number'], ['current_inventory', '当前库存', 'number'],
            ['contractor_inventory', '施工单位库存', 'number'], ['transit_quantity', '在途量', 'number'],
            ['required_date', '要求到场日期', 'date'], ['review_comment', '审核意见', 'textarea', '', 'wide']
        ]
    },
    transactions: {
        label: '收发记录',
        endpoint: 'transactions',
        fields: [
            ['business_date', '业务日期 *', 'date'], ['business_type', '业务类型 *', 'select', '到货|领用|退库|调拨入|调拨出'],
            ['building', '单位工程/楼栋'], ['construction_area', '施工部位'],
            ['material_name', '材料名称 *'], ['specification', '规格型号'], ['unit', '单位 *'],
            ['quantity', '数量', 'number'], ['supplier_source', '供应商/来源'], ['document_no', '送货单或领料单号'],
            ['acceptance_result', '验收结果'], ['quality_documents', '质量证明文件'], ['receiving_unit', '领用单位'],
            ['signer', '签收人'], ['registrant', '登记人'], ['remark', '备注', 'textarea', '', 'wide']
        ]
    },
    issues: {
        label: '预警问题',
        endpoint: 'issues',
        fields: [
            ['warning_date', '预警日期 *', 'date'], ['warning_status', '预警状态 *', 'select', '黄色|红色'],
            ['building', '单位工程/楼栋'], ['material_name', '材料名称 *'], ['specification', '规格型号'],
            ['variance_quantity', '偏差量', 'number'], ['loss_rate', '损耗率', 'number'],
            ['reason_category', '原因分类'], ['responsible_person', '责任人'], ['due_date', '完成期限', 'date'],
            ['closure_status', '闭环状态', 'select', '待处理|处理中|已闭环'], ['reviewer', '复核人'],
            ['problem_description', '问题描述 *', 'textarea', '', 'wide'],
            ['corrective_action', '整改措施', 'textarea', '', 'wide'], ['review_result', '复核结果', 'textarea', '', 'wide']
        ]
    },
    issue_review: {
        label: '更新闭环',
        endpoint: 'issues',
        fields: [
            ['closure_status', '闭环状态', 'select', '待处理|处理中|已闭环'],
            ['reviewer', '复核人'], ['review_result', '复核结果', 'textarea', '', 'wide']
        ]
    }
};

function ownerSuppliedQuery() {
    return currentProjectId ? `?project_id=${currentProjectId}` : '';
}

function ownerNum(value) {
    const num = Number(value || 0);
    return Number.isFinite(num) ? num.toLocaleString('zh-CN', { maximumFractionDigits: 3 }) : '-';
}

function ownerRate(value) {
    const num = Number(value || 0);
    return Number.isFinite(num) ? `${(num * 100).toFixed(2)}%` : '-';
}

function ownerDate(value) {
    return value ? String(value).slice(0, 10) : '-';
}

function ownerEmpty(colspan, message = '暂无记录') {
    return `<tr><td colspan="${colspan}" class="empty-message">${message}</td></tr>`;
}

function ownerWarning(status) {
    return `<span class="owner-warning owner-warning-${status === '红色' ? 'red' : status === '黄色' ? 'yellow' : 'green'}">${escapeHtml(status || '-')}</span>`;
}

async function loadOwnerSupplied() {
    await Promise.all([loadOwnerSuppliedSummary(), loadOwnerSuppliedList(ownerSuppliedTab)]);
}

async function loadOwnerSuppliedSummary() {
    try {
        const res = await api(`/api/owner-supplied/summary${ownerSuppliedQuery()}`);
        const data = await res.json();
        if (!data.success) return;
        const summary = data.data || {};
        document.getElementById('ownerMetricTotal').textContent = summary.total || 0;
        document.getElementById('ownerMetricAClass').textContent = summary.a_class || 0;
        document.getElementById('ownerMetricGreen').textContent = summary.green || 0;
        document.getElementById('ownerMetricYellow').textContent = summary.yellow || 0;
        document.getElementById('ownerMetricRed').textContent = summary.red || 0;
        document.getElementById('ownerMetricOpen').textContent = (summary.pending_issues || 0) + (summary.processing_issues || 0);
    } catch (e) {
        console.error('加载甲供材看板失败', e);
    }
}

async function switchOwnerSuppliedTab(tab) {
    ownerSuppliedTab = tab;
    document.querySelectorAll('.owner-tab').forEach(btn => btn.classList.toggle('active', btn.dataset.ownerTab === tab));
    document.querySelectorAll('.owner-tab-panel').forEach(panel => panel.classList.toggle('hidden', panel.dataset.ownerPanel !== tab));
    document.getElementById('ownerSuppliedAddBtn').textContent = `新增${ownerSuppliedConfigs[tab].label}`;
    await loadOwnerSuppliedList(tab);
}

async function loadOwnerSuppliedList(type) {
    try {
        const endpoint = ownerSuppliedConfigs[type].endpoint;
        const res = await api(`/api/owner-supplied/${endpoint}${ownerSuppliedQuery()}`);
        const data = await res.json();
        if (!data.success) {
            showToast(data.message || '加载失败', 'error');
            return;
        }
        ownerSuppliedRecords[type] = data.data || [];
        renderOwnerSuppliedTable(type);
    } catch (e) {
        console.error('加载甲供材记录失败', e);
        showToast('甲供材记录加载失败', 'error');
    }
}

function renderOwnerSuppliedTable(type) {
    const records = ownerSuppliedRecords[type] || [];
    if (type === 'controls') {
        document.getElementById('ownerControlsTable').innerHTML = records.length ? records.map(item => `
            <tr>
                <td>${ownerWarning(item.warning_status)}</td><td>${escapeHtml(item.control_level || '-')}</td>
                <td>${escapeHtml(item.building || '-')}</td><td>${escapeHtml(item.work_item || '-')}</td>
                <td>${escapeHtml(item.material_name || '-')}</td><td>${escapeHtml(item.specification || '-')}</td><td>${escapeHtml(item.unit || '-')}</td>
                <td>${ownerNum(item.current_control_quantity)}</td><td>${ownerNum(item.arrival_quantity)}</td><td>${ownerNum(item.issued_quantity)}</td>
                <td>${ownerNum(item.theoretical_quantity)}</td><td>${ownerNum(item.site_surplus)}</td><td>${ownerNum(item.book_inventory)}</td>
                <td>${ownerNum(item.transit_quantity)}</td><td>${ownerNum(item.remaining_requirement)}</td><td>${ownerNum(item.variance_quantity)}</td>
                <td>${ownerRate(item.loss_rate)}</td><td>${escapeHtml(item.responsible_person || '-')}</td>
                <td><button class="btn btn-secondary" onclick="editOwnerSuppliedControl(${item.id})">编辑</button> <button class="btn btn-danger" onclick="deleteOwnerSupplied('controls', ${item.id})">删除</button></td>
            </tr>`).join('') : ownerEmpty(19);
    } else if (type === 'demands') {
        document.getElementById('ownerDemandsTable').innerHTML = records.length ? records.map(item => `
            <tr><td>${ownerDate(item.plan_month)}</td><td>${escapeHtml(item.building || '-')}</td><td>${escapeHtml(item.construction_area || '-')}</td>
                <td>${escapeHtml(item.material_name || '-')}</td><td>${escapeHtml(item.specification || '-')}</td><td>${escapeHtml(item.unit || '-')}</td>
                <td>${ownerNum(item.planned_quantity)}</td><td>${ownerNum(item.current_inventory)}</td><td>${ownerNum(item.contractor_inventory)}</td>
                <td>${ownerNum(item.transit_quantity)}</td><td><strong>${ownerNum(item.recommended_supply)}</strong></td><td>${ownerDate(item.required_date)}</td>
                <td class="owner-long-text">${escapeHtml(item.review_comment || '-')}</td><td><button class="btn btn-danger" onclick="deleteOwnerSupplied('demands', ${item.id})">删除</button></td></tr>`).join('') : ownerEmpty(14);
    } else if (type === 'transactions') {
        document.getElementById('ownerTransactionsTable').innerHTML = records.length ? records.map(item => `
            <tr><td>${ownerDate(item.business_date)}</td><td>${escapeHtml(item.business_type || '-')}</td><td>${escapeHtml(item.building || '-')}</td>
                <td>${escapeHtml(item.construction_area || '-')}</td><td>${escapeHtml(item.material_name || '-')}</td><td>${escapeHtml(item.specification || '-')}</td>
                <td>${escapeHtml(item.unit || '-')}</td><td>${ownerNum(item.quantity)}</td><td>${escapeHtml(item.supplier_source || '-')}</td>
                <td>${escapeHtml(item.document_no || '-')}</td><td>${escapeHtml(item.acceptance_result || '-')}</td><td>${escapeHtml(item.receiving_unit || '-')}</td>
                <td>${escapeHtml(item.signer || '-')}</td><td>${escapeHtml(item.registrant || '-')}</td><td><button class="btn btn-danger" onclick="deleteOwnerSupplied('transactions', ${item.id})">删除</button></td></tr>`).join('') : ownerEmpty(15);
    } else if (type === 'issues') {
        document.getElementById('ownerIssuesTable').innerHTML = records.length ? records.map(item => `
            <tr><td>${ownerDate(item.warning_date)}</td><td>${ownerWarning(item.warning_status)}</td><td>${escapeHtml(item.building || '-')}</td>
                <td>${escapeHtml(item.material_name || '-')}</td><td>${escapeHtml(item.specification || '-')}</td><td>${ownerNum(item.variance_quantity)}</td>
                <td>${ownerRate(item.loss_rate)}</td><td class="owner-long-text">${escapeHtml(item.problem_description || '-')}</td>
                <td class="owner-long-text">${escapeHtml(item.corrective_action || '-')}</td><td>${escapeHtml(item.responsible_person || '-')}</td>
                <td>${ownerDate(item.due_date)}</td><td>${escapeHtml(item.closure_status || '-')}</td><td>${escapeHtml(item.reviewer || '-')}</td>
                <td><button class="btn btn-secondary" onclick="reviewOwnerSuppliedIssue(${item.id})">闭环</button> <button class="btn btn-danger" onclick="deleteOwnerSupplied('issues', ${item.id})">删除</button></td></tr>`).join('') : ownerEmpty(14);
    }
}

function openOwnerSuppliedCreate() {
    ownerSuppliedModal = { type: ownerSuppliedTab, id: null };
    openOwnerSuppliedModal(ownerSuppliedConfigs[ownerSuppliedTab], {});
}

function editOwnerSuppliedControl(id) {
    const record = ownerSuppliedRecords.controls.find(item => item.id === id);
    if (!record) return;
    ownerSuppliedModal = { type: 'controls', id };
    openOwnerSuppliedModal(ownerSuppliedConfigs.controls, record);
}

function reviewOwnerSuppliedIssue(id) {
    const record = ownerSuppliedRecords.issues.find(item => item.id === id);
    if (!record) return;
    ownerSuppliedModal = { type: 'issue_review', id };
    openOwnerSuppliedModal(ownerSuppliedConfigs.issue_review, record);
}

function ownerSuppliedProjectField(record) {
    if (ownerSuppliedModal.type === 'issue_review') return '';
    const selectedId = record.project_id || currentProjectId || userProjects[0]?.id || '';
    const projects = userProjects.length ? userProjects : [];
    const options = projects.map(project => `<option value="${project.id}" ${Number(selectedId) === Number(project.id) ? 'selected' : ''}>${escapeHtml(project.project_name || '')}</option>`).join('');
    return `<div class="form-group"><label>所属项目 *</label><select name="project_id" required><option value="">-- 选择项目 --</option>${options}</select></div>`;
}

function ownerSuppliedFieldHtml(field, record) {
    const [name, label, type = 'text', options = '', width = ''] = field;
    let value = record[name] ?? '';
    if (type === 'date' || type === 'month') value = value ? String(value).slice(0, type === 'month' ? 7 : 10) : '';
    const className = width === 'wide' ? 'form-group owner-field-wide' : 'form-group';
    if (type === 'select') {
        const optionHtml = options.split('|').map(option => `<option value="${escapeHtml(option)}" ${String(value) === option ? 'selected' : ''}>${escapeHtml(option)}</option>`).join('');
        return `<div class="${className}"><label>${label}</label><select name="${name}">${optionHtml}</select></div>`;
    }
    if (type === 'textarea') {
        return `<div class="${className}"><label>${label}</label><textarea name="${name}">${escapeHtml(String(value))}</textarea></div>`;
    }
    const step = type === 'number' ? ' step="0.001"' : '';
    return `<div class="${className}"><label>${label}</label><input type="${type}" name="${name}" value="${escapeHtml(String(value))}"${step}></div>`;
}

function openOwnerSuppliedModal(config, record) {
    document.getElementById('ownerSuppliedModalTitle').textContent = `${ownerSuppliedModal.id ? '编辑' : '新增'}${config.label}`;
    document.getElementById('ownerSuppliedFields').innerHTML = ownerSuppliedProjectField(record) + config.fields.map(field => ownerSuppliedFieldHtml(field, record)).join('');
    openModal('modal-owner-supplied');
}

async function submitOwnerSuppliedForm(event) {
    event.preventDefault();
    const config = ownerSuppliedConfigs[ownerSuppliedModal.type];
    const body = Object.fromEntries(new FormData(event.target).entries());
    const endpoint = `/api/owner-supplied/${config.endpoint}${ownerSuppliedModal.id ? `/${ownerSuppliedModal.id}` : ''}`;
    const method = ownerSuppliedModal.id ? 'PUT' : 'POST';
    try {
        const res = await api(endpoint, { method, body: JSON.stringify(body) });
        const data = await res.json();
        if (!data.success) {
            showToast(data.message || '保存失败', 'error');
            return;
        }
        closeModal('modal-owner-supplied');
        showToast('保存成功', 'success');
        await loadOwnerSupplied();
    } catch (e) {
        showToast('保存失败', 'error');
    }
}

async function deleteOwnerSupplied(type, id) {
    if (!confirm('确定删除该记录？')) return;
    try {
        const endpoint = ownerSuppliedConfigs[type].endpoint;
        const res = await api(`/api/owner-supplied/${endpoint}/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (!data.success) {
            showToast(data.message || '删除失败', 'error');
            return;
        }
        showToast('删除成功', 'success');
        await loadOwnerSupplied();
    } catch (e) {
        showToast('删除失败', 'error');
    }
}
