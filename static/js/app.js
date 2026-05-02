// 零星材管理系统 - 前端脚本
let currentUser = null;
let currentProjectId = null;
let userProjects = [];
let materials = [];
let suppliers = [];
let units = [];
let inquiryItems = [];
let stockInDetails = [];
let cartItems = [];

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

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', () => {
    // 初始化 Lucide 图标
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
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
        alert('请输入用户名和密码');
        return;
    }

    // 先清空旧状态，防止界面闪烁
    document.getElementById('mainPage').classList.add('hidden');
    document.getElementById('projectSelectPage').classList.add('hidden');
    document.getElementById('loginPage').classList.add('hidden');

    try {
        const res = await fetch('/api/login', {
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

            // 获取用户绑定的项目
            const projRes = await fetch('/api/projects?mine=1');
            const projData = await projRes.json();
            userProjects = projData.success ? projData.data : [];

            // 判断是否需要选择项目
            if (currentUser.role_name === '系统管理员' || userProjects.length <= 1) {
                // admin 或只有一个项目，直接进入
                if (userProjects.length === 1) {
                    currentProjectId = userProjects[0].id;
                    sessionStorage.setItem('currentProjectId', currentProjectId);
                }
                enterMainSystem();
            } else {
                // 多于一个项目，显示项目选择页面
                showProjectSelect();
            }
        } else {
            document.getElementById('loginPage').classList.remove('hidden');
            alert(data.message);
        }
    } catch (e) {
        document.getElementById('loginPage').classList.remove('hidden');
        alert('登录失败: ' + e.message);
    }
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
        alert('请选择项目');
        return;
    }
    currentProjectId = parseInt(projectId);
    sessionStorage.setItem('currentProjectId', currentProjectId);
    enterMainSystem();
}

async function openSwitchProjectModal() {
    if (userProjects.length <= 1) {
        alert('您只有一个绑定项目，无需切换');
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
        alert('请选择项目');
        return;
    }

    const newProj = userProjects.find(p => p.id === newProjectId);
    currentProjectId = newProjectId;
    sessionStorage.setItem('currentProjectId', currentProjectId);
    document.getElementById('selectedProjectName').textContent = newProj?.project_name;

    closeModal('modal-switch-project');
    alert('已切换到项目: ' + newProj?.project_name);
}

function enterMainSystem() {
    document.getElementById('loginPage').classList.add('hidden');
    document.getElementById('projectSelectPage').classList.add('hidden');
    document.getElementById('mainPage').classList.remove('hidden');

    document.getElementById('userInfo').textContent = `用户: ${currentUser.real_name}`;
    document.getElementById('userRoleDisplay').textContent = currentUser.role_name;

    // 显示项目信息和切换按钮
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
    await fetch('/api/logout', {method: 'POST'});
    currentUser = null;
    currentProjectId = null;
    userProjects = [];
    document.getElementById('mainPage').classList.add('hidden');
    document.getElementById('projectSelectPage').classList.add('hidden');
    document.getElementById('loginPage').classList.remove('hidden');
}

async function checkLogin() {
    try {
        const res = await fetch('/api/current_user');
        const data = await res.json();
        if (data.success) {
            currentUser = data.user;
            sessionStorage.setItem('currentUser', JSON.stringify(currentUser));

            const projRes = await fetch('/api/projects?mine=1');
            const projData = await projRes.json();
            userProjects = projData.success ? projData.data : [];

            currentProjectId = sessionStorage.getItem('currentProjectId') ? parseInt(sessionStorage.getItem('currentProjectId')) : null;
            if (currentProjectId && !userProjects.find(p => p.id === currentProjectId)) {
                currentProjectId = userProjects.length === 1 ? userProjects[0].id : null;
            }

            if (currentUser.role_name === '系统管理员' || userProjects.length <= 1) {
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
    event.target.closest('.nav-item').classList.add('active');

    switch(module) {
        case 'home': loadHome(); break;
        case 'material': loadMaterials(); break;
        case 'purchase_inquiry': loadInquiries(); break;
        case 'purchase_order': loadOrders(); break;
        case 'stock_in': loadStockIn(); break;
        case 'stock_out': loadStockOut(); break;
        case 'inventory': loadInventory(); break;
        case 'supplier': loadSuppliers(); break;
        case 'project': loadProjects(); break;
        case 'reconciliation': loadReconciliation(); break;
        case 'system': loadUsers(); break;
    }
}

// ==================== 首页 ====================

async function loadHome() {
    try {
        const res = await fetch('/api/dashboard');
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

// ==================== 材料管理 ====================

// 权限判断
function isAdmin() {
    const user = JSON.parse(sessionStorage.getItem('currentUser') || '{}');
    return user.role_name === '系统管理员';
}

function isMaterialClerk() {
    const user = JSON.parse(sessionStorage.getItem('currentUser') || '{}');
    return user.role_name === '材料员';
}

function canApprove() {
    return isAdmin();
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
    const keyword = document.getElementById('materialSearch')?.value || '';
    materialState.keyword = keyword;
    materialState.page = 1;
    materialState.allLoaded = false;

    // 保留原有DOM结构和CSS类名，只更新加载状态
    const tbody = document.getElementById('materialTable');
    if (tbody) {
        tbody.innerHTML = '<tr class="loading-row"><td colspan="9"><div class="loading-spinner">加载中...</div></td></tr>';
    }

    try {
        const res = await fetch(`/api/materials?keyword=${encodeURIComponent(keyword)}&page=1&page_size=${MATERIAL_PAGE_SIZE}`);
        const data = await res.json();
        if (data.success) {
            materials = data.data || [];
            materialState.total = data.total || 0;
            materialState.totalPages = data.total_pages || 1;
            materialState.allLoaded = materials.length >= materialState.total;
            renderMaterialTable();
            updateMaterialStats();
        }
    } catch (e) {
        console.error('加载材料失败', e);
        if (tbody) {
            tbody.innerHTML = '<tr class="error-row"><td colspan="9"><div class="error-message">加载失败，请重试</div></td></tr>';
        }
    }
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
            existingLoadMore.innerHTML = '<td colspan="9"><div class="loading-spinner">加载中...</div></td>';
        }
    }

    const nextPage = materialState.page + 1;
    try {
        const res = await fetch(`/api/materials?keyword=${encodeURIComponent(materialState.keyword)}&page=${nextPage}&page_size=${MATERIAL_PAGE_SIZE}`);
        const data = await res.json();
        if (data.success && data.data) {
            // 追加新数据，不清空现有数据
            materials = materials.concat(data.data || []);
            materialState.page = nextPage;
            materialState.allLoaded = materials.length >= data.total;
            renderMaterialTable();
        }
    } catch (e) {
        console.error('加载更多材料失败', e);
        // 恢复"加载更多"提示
        if (tbody) {
            const existingLoadMore = tbody.querySelector('.load-more-row');
            if (existingLoadMore) {
                existingLoadMore.innerHTML = '<td colspan="9"><div class="error-message">加载失败，请滚动重试</div></td>';
            }
        }
    } finally {
        materialState.loading = false;
    }
}

function renderMaterialTable() {
    const tbody = document.getElementById('materialTable');
    if (!tbody) return;

    // 空数据状态 - 保留DOM结构和CSS类名
    if (materials.length === 0) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="12"><div class="empty-message">暂无数据</div></td></tr>';
        return;
    }

    // 辅助函数：安全格式化数字
    const safeNum = (val, decimals = 2, prefix = '') => {
        const num = parseFloat(val);
        if (isNaN(num)) return prefix + '-';
        return prefix + num.toFixed(decimals);
    };

    // 辅助函数：安全格式化税率
    const safeRate = (val) => {
        const num = parseFloat(val);
        if (isNaN(num) || num === 0) return '-';
        return (num * 100).toFixed(0) + '%';
    };

    // 辅助函数：格式化是否国标
    const formatNationalStandard = (val) => {
        return val == 1 ? '是' : '否';
    };

    // 使用文档片段减少DOM操作
    const fragment = document.createDocumentFragment();
    materials.forEach(m => {
        const tr = document.createElement('tr');
        tr.className = 'material-row';
        tr.innerHTML = `
            <td class="col-code">${escapeHtml(m.material_code) || '-'}</td>
            <td class="col-name">${escapeHtml(m.material_name) || '-'}</td>
            <td class="col-spec">${escapeHtml(m.specification) || '-'}</td>
            <td class="col-detail-spec">${escapeHtml(m.detail_spec) || '-'}</td>
            <td class="col-national-standard">${formatNationalStandard(m.is_national_standard)}</td>
            <td class="col-brand">${escapeHtml(m.brand) || '-'}</td>
            <td class="col-unit">${escapeHtml(m.unit_name) || '-'}</td>
            <td class="col-rate">${safeRate(m.tax_rate)}</td>
            <td class="col-price">¥${safeNum(m.tax_price)}</td>
            <td class="col-no-tax">¥${safeNum(m.tax_exempt_price)}</td>
            <td class="col-supplier">${escapeHtml(m.supplier_name) || '-'}</td>
            <td class="col-actions">
                ${isAdmin() ? `<button class="btn btn-secondary" onclick="editMaterial(${m.id})">编辑</button>
                <button class="btn btn-danger" onclick="deleteMaterial(${m.id})">删除</button>` : ''}
                <button class="btn btn-primary" onclick="addToCart(${m.id})">加入询比价</button>
            </td>
        `;
        fragment.appendChild(tr);
    });

    // 如果还有更多数据，添加加载提示行
    if (!materialState.allLoaded) {
        const loadMoreTr = document.createElement('tr');
        loadMoreTr.className = 'load-more-row';
        loadMoreTr.innerHTML = '<td colspan="9"><div class="load-more-message">滚动加载更多...</div></td>';
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

// ==================== 采购购物车功能 ====================

function addToCart(materialId) {
    const m = materials.find(x => x.id == materialId);
    if (!m) return;
    // 检查是否已在购物车
    if (cartItems.some(c => c.material_id === materialId)) {
        alert('该材料已在询比价列表中');
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
    updateCartBadge();
    alert('已加入询比价列表');
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
            <td>${escapeHtml(c?.material_code || c?.['商品编号'] || '无编号')}</td>
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
    if (id) {
        await loadUnitsAndSuppliers();
        const m = materials.find(x => x.id === id);
        if (m) {
            document.getElementById('materialId').value = m.id;
            document.getElementById('materialCode').value = m.material_code || '';
            document.getElementById('materialCode').removeAttribute('readonly');
            document.getElementById('materialName').value = m.material_name;
            document.getElementById('materialSpec').value = m.specification || '';
            document.getElementById('materialDetailSpec').value = m.detail_spec || '';
            document.getElementById('materialNationalStandard').value = m.is_national_standard || 0;
            document.getElementById('materialBrand').value = m.brand || '';
            document.getElementById('materialTaxPrice').value = m.tax_price || 0;
            document.getElementById('materialTaxRate').value = m.tax_rate || 0.01;
            document.getElementById('materialRemark').value = m.remark || '';
            document.getElementById('materialUnit').value = m.unit_name || '';
            document.getElementById('materialSupplier').value = m.default_supplier_id || '';
            document.getElementById('materialModalTitle').textContent = '编辑材料';
        }
    } else {
        document.getElementById('materialForm').reset();
        document.getElementById('materialId').value = '';
        document.getElementById('materialDetailSpec').value = '';
        document.getElementById('materialNationalStandard').value = 0;
        document.getElementById('materialBrand').value = '';
        document.getElementById('materialModalTitle').textContent = '新建材料';
        await loadUnitsAndSuppliers();

        try {
            const res = await fetch(`/api/next-material-code?project_id=${currentProjectId}`);
            const data = await res.json();
            document.getElementById('materialCode').value = data.material_code || '';
            document.getElementById('materialCode').setAttribute('readonly', 'readonly');
        } catch (e) {
            document.getElementById('materialCode').value = '';
        }
    }

    openModal('modal-material');
}

async function editMaterial(id) {
    await openMaterialModal(id);
}

async function deleteMaterial(id) {
    if (!confirm('确定要删除该材料吗？')) return;

    try {
        const res = await fetch(`/api/materials/${id}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            alert('删除成功');
            loadMaterials();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('删除失败');
    }
}

async function deleteInquiry(id) {
    if (!confirm('确定要删除该询价单吗？')) return;

    try {
        const res = await fetch(`/api/purchase-inquiries/${id}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            alert('删除成功');
            loadInquiries();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('删除失败');
    }
}

document.getElementById('materialForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const supplierValue = document.getElementById('materialSupplier').value;
    const unitName = document.getElementById('materialUnit').value;
    const id = document.getElementById('materialId').value;

    const body = {
        material_code: document.getElementById('materialCode').value,
        material_name: document.getElementById('materialName').value,
        specification: document.getElementById('materialSpec').value,
        detail_spec: document.getElementById('materialDetailSpec').value,
        is_national_standard: parseInt(document.getElementById('materialNationalStandard').value) || 0,
        brand: document.getElementById('materialBrand').value,
        unit_name: unitName,
        tax_price: parseFloat(document.getElementById('materialTaxPrice').value) || 0,
        tax_rate: parseFloat(document.getElementById('materialTaxRate').value) || 0.01,
        default_supplier_id: supplierValue ? parseInt(supplierValue) : null,
        remark: document.getElementById('materialRemark').value
    };

    if (!id) {
        body.project_id = currentProjectId;
    }

    try {
        const url = id ? `/api/materials/${id}` : '/api/materials';
        const method = id ? 'PUT' : 'POST';
        const res = await fetch(url, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            alert(id ? '更新成功' : '创建成功');
            closeModal('modal-material');
            loadMaterials();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
});

// ==================== 询价单 ====================

async function loadInquiries() {
    try {
        const res = await fetch('/api/purchase-inquiries');
        const data = await res.json();
        if (data.success) {
            renderInquiryTable(data.data);
        }
    } catch (e) {
        alert('加载询价单失败');
    }
}

function renderInquiryTable(inquiries) {
    const tbody = document.getElementById('inquiryTable');
    tbody.innerHTML = inquiries.map(i => `
        <tr>
            <td>${i.inquiry_no}</td>
            <td>${i.inquiry_date || '-'}</td>
            <td>${i.applicant_name || '-'}</td>
            <td>¥${(i.total_amount || 0).toFixed(2)}</td>
            <td>${i.is_below_library_price == 1 ? '是' : '否'}</td>
            <td><span class="status ${getStatusClass(i.approval_status)}">${i.approval_status}</span></td>
            <td>
                <button class="btn btn-secondary" onclick="viewInquiry(${i.id})">查看</button>
                ${i.approval_status === '已同意' ? `<button class="btn btn-primary" onclick="printInquiryApproval(${i.id})">打印签字单</button>` : ''}
                ${i.approval_status === '待审批' && canApprove() ?
                    `<button class="btn btn-warning" onclick="approveInquiry(${i.id})">审批</button>` : ''}
                ${isAdmin() ?
                    `<button class="btn btn-danger" onclick="deleteInquiry(${i.id})">删除</button>` : ''}
            </td>
        </tr>
    `).join('');
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
        const cols = 7 + (options.showSelected ? 1 : 0);
        return `<table><thead><tr>
            <th>材料</th><th>规格</th><th>库内价</th>
            <th>供应商</th><th>本次报价</th><th>价差</th>
            ${options.showSelected ? '<th>拟定</th>' : ''}
            <th>最低价</th>
        </tr></thead><tbody>
            <tr><td colspan="${cols}" style="text-align:center;color:#999;">暂无明细</td></tr>
        </tbody></table>`;
    }

    // 按材料名+规格分组
    const groups = [];
    flatDetails.forEach(d => {
        const key = (d.material_name || '-') + '||' + (d.specification || '-');
        let group = groups.find(g => g.key === key);
        if (!group) {
            group = { key, material_name: d.material_name || '-', specification: d.specification || '-', library_price: d.library_price || 0, rows: [] };
            groups.push(group);
        }
        group.rows.push(d);
    });

    let html = `<table><thead><tr>
        <th>材料</th><th>规格</th><th>库内价</th>
        <th>供应商</th><th>本次报价</th><th>价差</th>
        ${options.showSelected ? '<th>拟定</th>' : ''}
        <th>最低价</th>
    </tr></thead><tbody>`;

    groups.forEach(g => {
        g.rows.forEach((d, i) => {
            const priceDiff = d.price_diff !== undefined ? d.price_diff : (d.quote_price || d.this_price || 0) - (d.library_price || 0);
            const diffColor = priceDiff < 0 ? 'var(--success)' : priceDiff > 0 ? 'var(--danger)' : 'var(--text-secondary)';
            const quotePrice = d.quote_price || d.this_price || 0;
            const lowestTag = d.is_lowest == 1 ? '<span class="status approved" style="font-size:11px;">最低</span>' : '';
            const selectedTag = options.showSelected && d.is_selected == 1 ? '<span class="status processing" style="font-size:11px;">✓</span>' : '';

            html += '<tr>';
            if (i === 0) {
                // 第一行：显示合并的材料名/规格/库内价
                const rowspan = g.rows.length > 1 ? ` rowspan="${g.rows.length}"` : '';
                html += `<td${rowspan} style="font-weight:500;vertical-align:middle;">${escapeHtml(g.material_name)}</td>`;
                html += `<td${rowspan} style="vertical-align:middle;">${escapeHtml(g.specification)}</td>`;
                html += `<td${rowspan} style="vertical-align:middle;">¥${g.library_price.toFixed(2)}</td>`;
            }
            html += `<td>${escapeHtml(d.supplier_name || '-')}</td>`;
            html += `<td>¥${quotePrice.toFixed(2)}</td>`;
            html += `<td style="color:${diffColor};font-weight:500;">${priceDiff >= 0 ? '+' : ''}¥${priceDiff.toFixed(2)}</td>`;
            if (options.showSelected) {
                html += `<td>${selectedTag || '-'}</td>`;
            }
            html += `<td>${lowestTag || '-'}</td>`;
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
        '已驳回': 'rejected'
    };
    return map[status] || '';
}

async function viewInquiry(id) {
    try {
        const res = await fetch(`/api/purchase-inquiries/${id}`);
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
                            supplier_name: '-',
                            library_price: item.library_price || 0,
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
                                supplier_name: q.supplier_name || '-',
                                library_price: item.library_price || 0,
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
            document.getElementById('detailContent').innerHTML = `
                <div class="card">
                    <p><strong>单号:</strong> ${i.inquiry_no}</p>
                    <p><strong>日期:</strong> ${i.inquiry_date || '-'}</p>
                    <p><strong>申请人:</strong> ${i.applicant_name || '-'}</p>
                    <p><strong>总金额:</strong> ¥${(i.total_amount || 0).toFixed(2)}</p>
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
        alert('加载详情失败');
    }
}

async function approveInquiry(id) {
    // 打开审批模态框，加载询价单详情和审批历史
    try {
        const [detailRes, historyRes] = await Promise.all([
            fetch(`/api/purchase-inquiries/${id}`),
            fetch(`/api/purchase-inquiries/${id}/approval-history`)
        ]);
        const detailData = await detailRes.json();
        const historyData = await historyRes.json();

        if (!detailData.success) {
            alert('加载询价单失败：' + (detailData.message || '未知错误'));
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
                        unit_name: item.unit_name || '-',
                        quantity: item.quantity || 1,
                        supplier_name: '-',
                        library_price: item.library_price || 0,
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
                            unit_name: item.unit_name || '-',
                            quantity: item.quantity || 1,
                            supplier_name: q.supplier_name || '-',
                            library_price: item.library_price || 0,
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
        document.getElementById('approvalTotalAmount').textContent = '¥' + (inquiry.total_amount || 0).toFixed(2);
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

        if (inquiry.approval_status === '待审批') {
            actionSection.style.display = '';
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
            `;
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
        alert('加载审批信息失败：' + e.message);
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
    const actionLabel = action === 'manager' ? '主管审批通过' : '驳回';
    if (!confirm(`确认执行「${actionLabel}」操作？`)) return;

    // 禁用按钮防止重复提交
    const btns = document.querySelectorAll('.approval-action-btn');
    btns.forEach(btn => btn.classList.add('loading'));

    try {
        const res = await fetch(`/api/purchase-inquiries/${id}/approve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action, remark})
        });
        const data = await res.json();
        if (data.success) {
            closeModal('modal-approval');
            loadInquiries();
            // 如果在首页也刷新统计数据
            if (typeof loadDashboard === 'function') loadDashboard();
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
        const res = await fetch('/api/stock-in');
        const data = await res.json();
        if (data.success) {
            renderStockInTable(data.data);
            applyPermissionControls();
        }
    } catch (e) {
        alert('加载入库单失败');
    }
}

function renderStockInTable(stockIn) {
    const tbody = document.getElementById('stockInTable');
    if (!stockIn || stockIn.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#999;">暂无入库记录</td></tr>';
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
            outBtnHtml = `<button class="btn btn-warning" style="padding:4px 12px;font-size:12px;" onclick="openStockOutModal(${s.material_id}, '${escapeHtml(s.material_name || '')}', '${escapeHtml(s.specification || '')}', ${s.unit_price || 0})">出库</button>`;
        } else if (currentStock <= 0) {
            // 库存为0 = 已全部出库
            stockBadge = '<span style="color:#e74c3c;font-weight:600;">0 <span style="font-weight:400;font-size:11px;">(已出完)</span></span>';
            rowStyle = 'style="background:#fff5f5;"';
            outBtnHtml = '<button class="btn" style="padding:4px 12px;font-size:12px;background:#ddd;color:#999;cursor:not-allowed;" disabled>已出完</button>';
        } else if (currentStock < inQty) {
            // 部分出库
            stockBadge = `<span style="color:#f39c12;font-weight:600;">${currentStock} <span style="font-weight:400;font-size:11px;">(部分出库)</span></span>`;
            rowStyle = 'style="background:#fffcf0;"';
            outBtnHtml = `<button class="btn btn-warning" style="padding:4px 12px;font-size:12px;" onclick="openStockOutModal(${s.material_id}, '${escapeHtml(s.material_name || '')}', '${escapeHtml(s.specification || '')}', ${s.unit_price || 0})">出库</button>`;
        } else {
            // 未出库，库存充足
            stockBadge = `<span style="color:#27ae60;font-weight:600;">${currentStock}</span>`;
            outBtnHtml = `<button class="btn btn-warning" style="padding:4px 12px;font-size:12px;" onclick="openStockOutModal(${s.material_id}, '${escapeHtml(s.material_name || '')}', '${escapeHtml(s.specification || '')}', ${s.unit_price || 0})">出库</button>`;
        }

        return `<tr ${rowStyle}>
            <td>${i + 1}</td>
            <td>${nameStr}</td>
            <td>${inQty} ${escapeHtml(s.unit_name || '')}</td>
            <td>${escapeHtml(s.supplier_name || '-')}</td>
            <td>¥${(s.unit_price || 0).toFixed(2)}</td>
            <td>${stockBadge}</td>
            <td>${escapeHtml(s.project_name || '-')}</td>
            <td>${s.in_time || '-'}</td>
            <td class="admin-only" style="white-space:nowrap;">
                ${outBtnHtml}
                <button class="btn btn-danger" style="padding:4px 12px;font-size:12px;" onclick="deleteStockIn(${s.id})">删除</button>
            </td>
            <td class="material-clerk-only" style="white-space:nowrap;">
                ${outBtnHtml}
            </td>
        </tr>`;
    }).join('');
}

async function deleteStockIn(id) {
    if (!confirm('确定要删除该入库记录吗？')) return;
    try {
        const res = await fetch(`/api/stock-in/${id}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            alert('删除成功');
            loadStockIn();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('删除失败');
    }
}

async function deleteStockOut(id) {
    if (!confirm('确定要删除该出库记录吗？')) return;
    try {
        const res = await fetch(`/api/stock-out/${id}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            alert('删除成功');
            loadStockOut();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('删除失败');
    }
}

async function deleteInventory(materialId) {
    if (!confirm('确定要删除该库存记录吗？')) return;
    try {
        const res = await fetch(`/api/inventory/${materialId}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            alert('删除成功');
            loadInventory();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('删除失败');
    }
}

// ==================== 出库操作 ====================

let currentStockOutItem = null;

// 查看材料的出库历史记录
async function viewStockOutRecords(materialId, materialName) {
    try {
        const res = await fetch(`/api/stock-out/by-material/${materialId}`);
        const data = await res.json();
        if (!data.success) {
            alert('加载出库记录失败');
            return;
        }
        const records = data.data || [];
        document.getElementById('stockOutRecordsTitle').textContent = `${materialName} - 出库记录`;

        const tbody = document.getElementById('stockOutRecordsTable');
        if (records.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#999;">暂无出库记录</td></tr>';
        } else {
            tbody.innerHTML = records.map((r, i) => `
                <tr>
                    <td>${i + 1}</td>
                    <td>${escapeHtml(r.order_no || '-')}</td>
                    <td>${r.quantity || 0}</td>
                    <td>${r.out_time || '-'}</td>
                    <td>${escapeHtml(r.team_name || '-')}</td>
                    <td>${escapeHtml(r.receiver_name || '-')}</td>
                    <td>${escapeHtml(r.operator_name || '-')}</td>
                </tr>
            `).join('');
        }
        openModal('modal-stock-out-records');
    } catch (e) {
        alert('加载出库记录失败');
    }
}

async function openStockOutModal(materialId, materialName, spec, unitPrice) {
    // 从库存API查实时库存
    let stockQty = 0;
    try {
        const res = await fetch('/api/inventory');
        const data = await res.json();
        const inv = (data.data || []).find(i => i.material_id == materialId);
        if (inv) {
            stockQty = inv.quantity || 0;
        }
    } catch (e) {
        console.error('查询库存失败:', e);
    }

    if (stockQty <= 0) {
        alert('该材料库存为0，无法出库');
        return;
    }

    currentStockOutItem = {
        materialId: materialId,
        materialName: materialName,
        specification: spec,
        stockQty: stockQty,
        unitPrice: unitPrice
    };

    document.getElementById('stockOutMaterialName').value = materialName;
    document.getElementById('stockOutSpec').value = spec || '-';
    document.getElementById('stockOutStockQty').value = stockQty;
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
        alert('请输入有效的出库数量');
        return;
    }
    if (quantity > currentStockOutItem.stockQty) {
        alert('出库数量不能大于库存数量(' + currentStockOutItem.stockQty + ')');
        return;
    }
    if (!teamName && !receiverName) {
        alert('请填写领用班组或领用人');
        return;
    }

    try {
        const res = await fetch('/api/stock-out', {
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
                remark: remark
            })
        });
        const data = await res.json();
        if (data.success) {
            alert('出库成功！单号: ' + data.order_no);
            closeModal('modal-stock-out');
            currentStockOutItem = null;
            loadStockIn();
        } else {
            alert('出库失败: ' + data.message);
        }
    } catch (err) {
        alert('出库请求失败');
    }
}

// ==================== 出库管理 ====================

async function loadStockOut() {
    try {
        const res = await fetch('/api/stock-out');
        const data = await res.json();
        if (data.success) {
            renderStockOutTable(data.data);
            applyPermissionControls();
        }
    } catch (e) {
        alert('加载出库单失败');
    }
}

function renderStockOutTable(stockOut) {
    const tbody = document.getElementById('stockOutTable');
    if (!stockOut || stockOut.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#999;">暂无出库记录</td></tr>';
        return;
    }
    tbody.innerHTML = stockOut.map((s, i) => `
        <tr>
            <td>${i + 1}</td>
            <td>${escapeHtml(s.material_name || '-')}</td>
            <td>${escapeHtml(s.specification || '-')}</td>
            <td>${s.quantity || 0} ${escapeHtml(s.unit_name || '')}</td>
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
        const res = await fetch('/api/inventory');
        const data = await res.json();
        if (data.success) {
            renderInventoryTable(data.data);
            applyPermissionControls();
        }
    } catch (e) {
        alert('加载库存失败');
    }
}

function renderInventoryTable(inventory) {
    const tbody = document.getElementById('inventoryTable');
    tbody.innerHTML = (inventory || []).map((i, idx) => `
        <tr>
            <td>${idx + 1}</td>
            <td>${i.material_name || '-'}</td>
            <td>${i.specification || '-'}</td>
            <td>${i.warehouse_name || '-'}</td>
            <td>${i.quantity || 0}</td>
            <td>¥${(i.unit_price || 0).toFixed(2)}</td>
            <td>¥${((i.quantity || 0) * (i.unit_price || 0)).toFixed(2)}</td>
            <td class="admin-only"><button class="btn btn-danger" style="padding:4px 12px;font-size:12px;" onclick="deleteInventory(${i.material_id})">删除</button></td>
        </tr>
    `).join('') || '<tr><td colspan="8" class="loading">暂无数据</td></tr>';
}

// ==================== 供应商管理 ====================

async function loadSuppliers() {
    try {
        const res = await fetch('/api/suppliers');
        const data = await res.json();
        if (data.success) {
            suppliers = data.data;
            renderSupplierTable();
            applyPermissionControls();
        }
    } catch (e) {
        alert('加载供应商失败');
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
        const res = await fetch(`/api/suppliers/${id}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            alert('删除成功');
            loadSuppliers();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('删除失败');
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
        const res = await fetch(url, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            alert(id ? '更新成功' : '创建成功');
            closeModal('modal-supplier');
            resetSupplierModal();
            loadSuppliers();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('保存失败');
    }
});

// ==================== 对账管理 ====================

async function loadReconciliation() {
    try {
        const res = await fetch('/api/reconciliation');
        const data = await res.json();
        if (data.success) {
            renderReconciliationTable(data.data);
        }
    } catch (e) {
        alert('加载对账单失败');
    }
}

function renderReconciliationTable(statements) {
    const tbody = document.getElementById('reconciliationTable');
    tbody.innerHTML = (statements || []).map(s => {
        const statusClass = s.status === '已打印' ? 'completed' : s.status === '已确认' ? 'approved' : 'pending';
        const isAdminUser = isAdmin();
        const canConfirm = s.status === '草稿' && isAdminUser;
        const canDelete = s.status === '草稿' && isAdminUser;
        const canPrint = s.status === '已确认' || s.status === '已打印';

        return `
        <tr>
            <td>${escapeHtml(s.statement_no || '')}</td>
            <td>${escapeHtml(s.supplier_name || '-')}</td>
            <td>${s.period_start || '-'} ~ ${s.period_end || '-'}</td>
            <td>¥${(s.total_amount || 0).toFixed(2)}</td>
            <td><span class="status ${statusClass}">${escapeHtml(s.status || '草稿')}</span></td>
            <td>
                <button class="btn btn-secondary" onclick="viewReconciliation(${s.id})">查看</button>
                ${canConfirm ? `<button class="btn btn-warning" onclick="confirmReconciliation(${s.id})" style="font-size:12px;padding:4px 10px;">确认</button>` : ''}
                ${canPrint ? `<button class="btn btn-primary" onclick="printReconciliation(${s.id})">打印</button>` : ''}
                ${canDelete ? `<button class="btn btn-danger" onclick="deleteReconciliation(${s.id})" style="font-size:12px;padding:4px 10px;">删除</button>` : ''}
            </td>
        </tr>`;
    }).join('') || '<tr><td colspan="6" class="loading">暂无数据</td></tr>';
}

async function viewReconciliation(id) {
    try {
        const res = await fetch(`/api/reconciliation/${id}`);
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
        alert('加载详情失败');
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
        const res = await fetch(`/api/reconciliation/${id}/confirm`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast('对账单已确认', 'success');
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
        const res = await fetch(`/api/reconciliation/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            showToast('对账单已删除', 'success');
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
        const supplierRes = await fetch('/api/suppliers');
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

    // 加载项目
    try {
        const res = await fetch('/api/projects');
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

        const res = await fetch(`/api/reconciliation/supplier-purchases?${params}`);
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
            showToast(`已自动填充 ${reconDetails.length} 条采购记录`, 'success');
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
        const res = await fetch('/api/reconciliation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            showToast('对账单创建成功！', 'success');
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
    return fetch(url).then(res => res.json()).then(data => {
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
    try {
        const supRes = await fetch('/api/suppliers');
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

// ==================== 询价单明细操作（嵌套比价结构）====================

function addInquiryItem() {
    const item = {
        material_id: '',
        material_name: '',
        material_code: '',
        specification: '',
        unit_name: '',
        quantity: 1,
        library_price: 0,
        selected_quote_id: null,
        quotes: [
            { supplier_id: '', supplier_name: '', tax_price: 0, tax_exempt_price: 0, tax_rate: 0.13, total_amount: 0, is_lowest: false, is_selected: false },
            { supplier_id: '', supplier_name: '', tax_price: 0, tax_exempt_price: 0, tax_rate: 0.13, total_amount: 0, is_lowest: false, is_selected: false },
            { supplier_id: '', supplier_name: '', tax_price: 0, tax_exempt_price: 0, tax_rate: 0.13, total_amount: 0, is_lowest: false, is_selected: false }
        ]
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
    const m = (materials || []).find(x => x?.id == materialId);
    if (m) {
        item.material_id = m.id;
        item.material_name = m.material_name || '';
        item.material_code = m.material_code || '';
        item.specification = m.specification || '';
        item.unit_name = m.unit_name || '';
        item.library_price = m.tax_price || 0;
    }
    renderInquiryItems();
}

function updateQuoteField(itemIndex, quoteIndex, field, value) {
    const item = inquiryItems[itemIndex];
    if (!item || !item.quotes[quoteIndex]) return;

    const quote = item.quotes[quoteIndex];
    const numValue = parseFloat(value) || 0;

    quote[field] = numValue;

    // 自动计算不含税单价和总金额
    if (field === 'tax_price') {
        quote.tax_exempt_price = numValue > 0 ? (numValue / (1 + quote.tax_rate)) : 0;
        quote.total_amount = numValue * item.quantity;
    } else if (field === 'tax_exempt_price') {
        quote.tax_price = numValue > 0 ? (numValue * (1 + quote.tax_rate)) : 0;
        quote.total_amount = quote.tax_price * item.quantity;
    }

    // 更新最低价标记
    updateLowestFlag(itemIndex);

    renderInquiryItems();
    updateInquiryTotal();
}

function updateItemQuantity(itemIndex, quantity) {
    const item = inquiryItems[itemIndex];
    item.quantity = parseFloat(quantity) || 1;

    // 重新计算所有报价的总金额
    item.quotes.forEach(q => {
        q.total_amount = (q.tax_price || 0) * item.quantity;
    });

    updateLowestFlag(itemIndex);
    renderInquiryItems();
    updateInquiryTotal();
}

function updateLowestFlag(itemIndex) {
    const item = inquiryItems[itemIndex];
    const validQuotes = item.quotes.filter(q => q.supplier_id && q.tax_price > 0);

    // 重置所有报价的 is_lowest 标记
    item.quotes.forEach(q => q.is_lowest = false);

    if (validQuotes.length === 0) return;

    // 找出最低价
    const lowest = validQuotes.reduce((min, q) =>
        (q.total_amount || 0) < (min.total_amount || 0) ? q : min, validQuotes[0]);
    lowest.is_lowest = true;
}

function selectQuote(itemIndex, quoteIndex) {
    const item = inquiryItems[itemIndex];

    // 重置所有选中状态
    item.quotes.forEach(q => q.is_selected = false);
    item.quotes[quoteIndex].is_selected = true;
    item.selected_quote_id = item.quotes[quoteIndex].supplier_id;

    renderInquiryItems();
    updateInquiryTotal();
}

function updateQuoteSupplier(itemIndex, quoteIndex, supplierId) {
    const item = inquiryItems[itemIndex];
    const quote = item.quotes[quoteIndex];

    const supplier = (suppliers || []).find(s => s.id == supplierId);
    quote.supplier_id = supplierId;
    quote.supplier_name = supplier ? supplier.supplier_name : '';

    // 同层供应商联动：其他材料的同一层报价也设为相同供应商
    inquiryItems.forEach((otherItem, otherIdx) => {
        if (otherIdx !== itemIndex && otherItem.quotes[quoteIndex]) {
            otherItem.quotes[quoteIndex].supplier_id = supplierId;
            otherItem.quotes[quoteIndex].supplier_name = supplier ? supplier.supplier_name : '';
        }
    });

    updateLowestFlag(itemIndex);
    renderInquiryItems();
    updateInquiryTotal();
}

function renderInquiryItems() {
    const container = document.getElementById('inquiryItemsContainer');
    if (!container) return;

    const validMaterials = materials || [];
    const validSuppliers = suppliers || [];

    if (inquiryItems.length === 0) {
        container.innerHTML = '<div class="empty-hint">请添加询价材料</div>';
        return;
    }

    container.innerHTML = inquiryItems.map((item, itemIndex) => `
        <div class="inquiry-item-card">
            <div class="item-header">
                <div class="item-info">
                    <select onchange="onMaterialSelect(${itemIndex}, this.value)">
                        <option value="">--请选择材料--</option>
                        ${validMaterials.map(m => `<option value="${m?.id}" ${item.material_id == m?.id ? 'selected' : ''}>${escapeHtml(m?.material_code || '')}${m?.specification ? ' ' + escapeHtml(m.specification) : ''} - ${escapeHtml(m?.material_name || '')}</option>`).join('')}
                    </select>
                    ${item.material_code ? `<span class="material-code">${escapeHtml(item.material_code)}</span>` : ''}
                    ${item.specification ? `<span class="material-spec">${escapeHtml(item.specification)}</span>` : ''}
                    ${item.unit_name ? `<span class="unit">单位: ${escapeHtml(item.unit_name)}</span>` : ''}
                    <span class="library-price-badge">库内价: ¥${(item.library_price || 0).toFixed(2)}</span>
                </div>
                <div class="item-quantity">
                    <label>采购数量:</label>
                    <input type="number" step="1" class="qty-input" value="${item.quantity}"
                           onchange="updateItemQuantity(${itemIndex}, this.value)">
                </div>
                <button type="button" class="btn btn-danger btn-sm" onclick="removeInquiryItem(${itemIndex})">删除材料</button>
            </div>

            <div class="quotes-grid">
                ${item.quotes.map((quote, quoteIndex) => `
                    <div class="quote-row ${quote.is_lowest ? 'lowest' : ''} ${quote.is_selected ? 'selected' : ''}">
                        ${quote.is_lowest ? '<div class="lowest-badge">最低价</div>' : ''}

                        <div class="quote-supplier">
                            <label>供应商</label>
                            <select onchange="updateQuoteSupplier(${itemIndex}, ${quoteIndex}, this.value)">
                                <option value="">--选择供应商--</option>
                                ${validSuppliers.map(s => `<option value="${s?.id}" ${quote.supplier_id == s?.id ? 'selected' : ''}>${escapeHtml(s?.supplier_name || '')}</option>`).join('')}
                            </select>
                        </div>

                        <div class="quote-inputs">
                            <div class="input-group">
                                <label>含税单价</label>
                                <input type="number" step="0.01" value="${quote.tax_price || ''}"
                                       onchange="updateQuoteField(${itemIndex}, ${quoteIndex}, 'tax_price', this.value)"
                                       placeholder="0.00">
                                ${quote.tax_price > 0 ? (() => {
                                    const diff = parseFloat(quote.tax_price) - parseFloat(item.library_price || 0);
                                    const pct = item.library_price > 0 ? ((diff / item.library_price) * 100).toFixed(1) : '';
                                    const color = diff < 0 ? 'var(--success)' : diff > 0 ? 'var(--danger)' : 'var(--text-muted)';
                                    const arrow = diff < 0 ? '↓' : diff > 0 ? '↑' : '=';
                                    return `<span class="price-diff-hint" style="color:${color};">比库内价 ${arrow} ¥${Math.abs(diff).toFixed(2)}${pct ? ' (' + pct + '%)' : ''}</span>`;
                                })() : ''}
                            </div>
                            <div class="input-group">
                                <label>不含税单价</label>
                                <input type="number" step="0.01" value="${quote.tax_exempt_price ? quote.tax_exempt_price.toFixed(2) : ''}"
                                       onchange="updateQuoteField(${itemIndex}, ${quoteIndex}, 'tax_exempt_price', this.value)"
                                       placeholder="0.00" readonly>
                            </div>
                        </div>

                        <div class="quote-amount">
                            <label>报价金额</label>
                            <div class="amount-value">¥${(quote.total_amount || 0).toFixed(2)}</div>
                        </div>

                        <div class="quote-actions">
                            <button type="button" class="btn ${quote.is_selected ? 'btn-primary' : 'btn-outline'}"
                                    onclick="selectQuote(${itemIndex}, ${quoteIndex})">
                                ${quote.is_selected ? '已选定' : '设为拟定'}
                            </button>
                        </div>
                    </div>
                `).join('')}
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

// 重写购物车生成询价单的逻辑（适配新结构）
async function generateInquiryFromCart() {
    const rawCart = cartItems || [];
    const validCart = rawCart.filter(item => item != null && item != undefined);
    if (validCart.length === 0) {
        alert('购物车为空');
        return;
    }

    console.log('=== generateInquiryFromCart START ===');
    console.log('validCart count:', validCart.length);

    // 将购物车数据转换为新的 items 结构
    inquiryItems = validCart.map(item => {
        const materialId = parseInt(item?.material_id || item?.['商品编号'], 10) || '';
        const m = (materials || []).find(x => x?.id == materialId);

        return {
            material_id: materialId,
            material_name: m?.material_name || item?.['商品名称'] || '',
            material_code: m?.material_code || item?.['商品编码'] || '',
            specification: m?.specification || '',
            unit_name: m?.unit_name || '',
            quantity: parseFloat(item?.quantity || 1),
            library_price: m?.tax_price || 0,
            selected_quote_id: null,
            quotes: [
                { supplier_id: '', supplier_name: '', tax_price: 0, tax_exempt_price: 0, tax_rate: 0.13, total_amount: 0, is_lowest: false, is_selected: false },
                { supplier_id: '', supplier_name: '', tax_price: 0, tax_exempt_price: 0, tax_rate: 0.13, total_amount: 0, is_lowest: false, is_selected: false },
                { supplier_id: '', supplier_name: '', tax_price: 0, tax_exempt_price: 0, tax_rate: 0.13, total_amount: 0, is_lowest: false, is_selected: false }
            ]
        };
    });

    closeCartDrawer();

    // 先标记modal已加载，防止openModal重复触发初始化逻辑
    const modal = document.getElementById('modal-inquiry');
    if (modal) modal.dataset.loaded = 'true';

    // 设置默认日期
    document.getElementById('inquiryDate').value = new Date().toISOString().split('T')[0];

    // 等待材料数据加载完成后再渲染
    await loadUnitsAndSuppliers();

    // 加载项目下拉（购物车生成询价单也需要加载）
    await loadProjectsToInquirySelect();

    modal.classList.add('show');

    // 渲染明细到表格
    renderInquiryItems();
    updateInquiryTotal();

    console.log('=== generateInquiryFromCart END ===');
    console.log('inquiryItems:', JSON.stringify(inquiryItems, null, 2));
}

async function submitInquiryForm() {
    // 深拷贝 inquiryItems 避免修改原始数据
    const rawItems = (inquiryItems || []).filter(item => item && item.material_id);

    if (rawItems.length === 0) {
        alert('请添加有效的询价材料（需选择材料）');
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
            quotes: quotes
        };
    }).filter(item => !isNaN(item.material_id) && item.material_id > 0);

    if (items.length === 0) {
        alert('请添加有效的询价材料（材料ID无效）');
        return;
    }

    // 检查是否有至少一条有效报价
    const hasAnyQuote = items.some(item => item.quotes.length > 0);
    if (!hasAnyQuote) {
        alert('请至少为一种材料填写供应商报价');
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
        const res = await fetch('/api/purchase-inquiries', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(requestData)
        });
        const data = await res.json();
        console.log('Response data:', data);
        if (data.success) {
            alert(`询价单创建成功！\n单号: ${data.inquiry_no}`);
            closeModal('modal-inquiry');
            inquiryItems = [];
            loadInquiries();
        } else {
            alert(data.message);
        }
    } catch (e) {
        console.error('Fetch error:', e);
        alert('创建失败: ' + e.message);
    }
}

// ==================== 入库单明细操作 ====================

// ==================== 入库单明细操作 ====================

async function openStockInModal() {
    await loadUnitsAndSuppliers();
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
                    ${materials.map(m => `<option value="${m.id}" ${d.material_id == m.id ? 'selected' : ''}>${m.material_code} - ${m.material_name}</option>`).join('')}
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
        const m = materials.find(x => x.id == value);
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
        alert('请添加有效的入库明细');
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
        const res = await fetch('/api/stock-in', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            alert(`入库单创建成功！\n单号: ${data.order_no}`);
            closeModal('modal-stock-in');
            stockInDetails = [];
            loadStockIn();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('创建失败');
    }
});

// ==================== 模态框控制 ====================

function openModal(id) {
    const modal = document.getElementById(id);
    modal.classList.add('show');

    // 打开询价单模态框时加载数据（只加载一次）
    if (id === 'modal-inquiry' && !modal.dataset.loaded) {
        // 设置默认日期为今天
        document.getElementById('inquiryDate').value = new Date().toISOString().split('T')[0];
        loadUnitsAndSuppliers().then(() => {
            if (inquiryItems.length === 0) {
                addInquiryItem();
            }
        });
        // 加载项目下拉
        loadProjectsToInquirySelect();
        modal.dataset.loaded = 'true';
    }
    // 打开入库单模态框时加载数据
    if (id === 'modal-stock-in' && !modal.dataset.loaded) {
        loadUnitsAndSuppliers();
        modal.dataset.loaded = 'true';
    }
    // 打开对账单模态框时初始化
    if (id === 'modal-reconciliation') {
        initReconForm();
    }
}

function closeModal(id) {
    document.getElementById(id).classList.remove('show');
}

// 点击模态框外部关闭
document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('show');
        }
    });
});

// ==================== 系统设置 ====================

let allUsers = [];
let allRoles = [];

async function loadUsers() {
    try {
        const [usersRes, rolesCached] = await Promise.all([
            fetch('/api/users'),
            loadCacheOrFetch('dict_roles', '/api/roles')
        ]);
        const usersData = await usersRes.json();
        const rolesData = rolesCached;

        allUsers = usersData.success ? usersData.data : [];
        allRoles = rolesData.success ? rolesData.data : [];

        renderUserTable();
    } catch (e) {
        alert('加载用户失败');
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
        const res = await fetch(`/api/users/${id}`, {method: 'DELETE'});
        const data = await res.json();
        if (data.success) {
            alert('删除成功');
            loadUsers();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('删除失败');
    }
}

async function loadRolesToSelect() {
    try {
        const res = await fetch('/api/roles');
        const data = await res.json();
        if (data.success) {
            const roleSelect = document.getElementById('userRole');
            roleSelect.innerHTML = data.data.map(r => `<option value="${r.id}">${r.role_name}</option>`).join('');
        }
    } catch (e) {}
}

async function loadProjectsToCheckboxes(selectedProjects = []) {
    try {
        const res = await fetch('/api/projects');
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
        const res = await fetch('/api/projects?mine=1');
        const data = await res.json();
        const select = document.getElementById('inquiryProject');
        if (!select) return;
        select.innerHTML = '<option value="">--选择项目--</option>';
        const projects = data.data || [];
        projects.forEach(p => {
            select.innerHTML += `<option value="${p.id}">${escapeHtml(p.project_name)}</option>`;
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
        const res = await fetch(url, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            alert(id ? '更新成功' : '创建成功');
            closeModal('modal-user');
            loadUsers();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('保存失败');
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
        const res = await fetch('/api/projects');
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
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#999;">暂无项目，点击上方按钮新建</td></tr>';
        return;
    }

    tbody.innerHTML = allProjects.map(p => `
        <tr>
            <td><strong>${escapeHtml(p.project_code || '')}</strong></td>
            <td>${escapeHtml(p.project_name || '')}</td>
            <td>${escapeHtml(p.contract_no || '-')}</td>
            <td>${escapeHtml(p.customer_name || '-')}</td>
            <td>${p.start_date || '-'}</td>
            <td>${p.end_date || '-'}</td>
            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(p.remark || '')}">${escapeHtml(p.remark || '-')}</td>
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
        const res = await fetch('/api/customers');
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
        const res = await fetch(`/api/projects/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            loadProjects();
        } else {
            alert(data.message || '删除失败');
        }
    } catch (e) {
        alert('删除失败');
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
        alert('项目名称不能为空');
        return;
    }

    try {
        const url = id ? `/api/projects/${id}` : '/api/projects';
        const method = id ? 'PUT' : 'POST';
        const res = await fetch(url, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            showToast(id ? '项目更新成功' : '项目创建成功', 'success');
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
