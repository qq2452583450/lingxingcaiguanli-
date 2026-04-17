// 零星材管理系统 - 前端脚本
let currentUser = null;
let materials = [];
let suppliers = [];
let units = [];
let inquiryDetails = [];
let stockInDetails = [];

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

    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username, password})
        });
        const data = await res.json();

        if (data.success) {
            currentUser = data.user;
            document.getElementById('loginPage').classList.add('hidden');
            document.getElementById('mainPage').classList.remove('hidden');
            document.getElementById('userInfo').textContent = `用户: ${currentUser.real_name}`;
            document.getElementById('userRole').textContent = currentUser.role_name;
            // 重新初始化 Lucide 图标（主页初始隐藏）
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
            // 登录后清除字典缓存，确保获取最新数据
            clearDictCache();
            // 绑定材料搜索和虚拟滚动
            bindMaterialSearch();
            initMaterialVirtualScroll();
            loadHome();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('登录失败: ' + e.message);
    }
}

async function logout() {
    await fetch('/api/logout', {method: 'POST'});
    currentUser = null;
    document.getElementById('mainPage').classList.add('hidden');
    document.getElementById('loginPage').classList.remove('hidden');
}

async function checkLogin() {
    try {
        const res = await fetch('/api/current_user');
        const data = await res.json();
        if (data.success) {
            currentUser = data.user;
            document.getElementById('loginPage').classList.add('hidden');
            document.getElementById('mainPage').classList.remove('hidden');
            document.getElementById('userInfo').textContent = `用户: ${currentUser.real_name}`;
            document.getElementById('userRole').textContent = currentUser.role_name;
            loadHome();
        }
    } catch (e) {
        // 未登录
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
    materials = [];

    const tbody = document.getElementById('materialTable');
    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="9" class="loading">加载中...</td></tr>';
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
            tbody.innerHTML = '<tr><td colspan="9" class="loading">加载失败</td></tr>';
        }
    }
}

// 加载更多材料（触底懒加载）
async function loadMoreMaterials() {
    if (materialState.loading || materialState.allLoaded) return;
    materialState.loading = true;

    const nextPage = materialState.page + 1;
    try {
        const res = await fetch(`/api/materials?keyword=${encodeURIComponent(materialState.keyword)}&page=${nextPage}&page_size=${MATERIAL_PAGE_SIZE}`);
        const data = await res.json();
        if (data.success && data.data) {
            materials = materials.concat(data.data || []);
            materialState.page = nextPage;
            materialState.allLoaded = materials.length >= data.total;
            renderMaterialTable();
        }
    } catch (e) {
        console.error('加载更多材料失败', e);
    } finally {
        materialState.loading = false;
    }
}

function renderMaterialTable() {
    const tbody = document.getElementById('materialTable');
    if (!tbody) return;

    if (materials.length === 0) {
        tbody.innerHTML = '<tr><td colspan="11" class="loading">暂无数据</td></tr>';
        return;
    }

    tbody.innerHTML = materials.map(m => `
        <tr>
            <td>${escapeHtml(m.material_code)}</td>
            <td>${escapeHtml(m.material_name)}</td>
            <td>${escapeHtml(m.specification || '-')}</td>
            <td>${escapeHtml(m.unit_name || '-')}</td>
            <td>${((m.tax_rate || 0.01) * 100).toFixed(0)}%</td>
            <td>¥${(m.tax_price || 0).toFixed(2)}</td>
            <td>¥${(m.tax_exempt_price || 0).toFixed(2)}</td>
            <td>${escapeHtml(m.supplier_name || '-')}</td>
            <td>${m.inventory_min || 0}</td>
            <td>${m.inventory_max || 0}</td>
            <td>
                <button class="btn btn-secondary" onclick="editMaterial(${m.id})">编辑</button>
                <button class="btn btn-danger" onclick="deleteMaterial(${m.id})">删除</button>
            </td>
        </tr>
    `).join('');

    // 如果还有更多数据，添加加载提示
    if (!materialState.allLoaded) {
        tbody.insertAdjacentHTML('beforeend', '<tr class="load-more-trigger"><td colspan="9" style="text-align:center;padding:10px;color:#999;">滚动加载更多...</td></tr>');
    }
}

function updateMaterialStats() {
    const statsEl = document.getElementById('materialStats');
    if (statsEl) {
        statsEl.textContent = `共 ${materialState.total} 条，当前显示 ${materials.length} 条`;
    }
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

    if (id) {
        const m = materials.find(x => x.id === id);
        if (m) {
            document.getElementById('materialId').value = m.id;
            document.getElementById('materialName').value = m.material_name;
            document.getElementById('materialSpec').value = m.specification || '';
            document.getElementById('materialTaxPrice').value = m.tax_price || 0;
            document.getElementById('materialTaxRate').value = m.tax_rate || 0.01;
            document.getElementById('materialFreight').value = m.freight || 0;
            document.getElementById('materialMin').value = m.inventory_min || 0;
            document.getElementById('materialMax').value = m.inventory_max || 0;
            document.getElementById('materialRemark').value = m.remark || '';
            document.getElementById('materialUnit').value = m.unit_id || '';
            document.getElementById('materialSupplier').value = m.default_supplier_id || '';
            document.getElementById('materialModalTitle').textContent = '编辑材料';
        }
    } else {
        document.getElementById('materialForm').reset();
        document.getElementById('materialId').value = '';
        document.getElementById('materialModalTitle').textContent = '新建材料';
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

document.getElementById('materialForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const id = document.getElementById('materialId').value;
    const body = {
        material_name: document.getElementById('materialName').value,
        specification: document.getElementById('materialSpec').value,
        unit_id: document.getElementById('materialUnit').value || null,
        tax_price: parseFloat(document.getElementById('materialTaxPrice').value) || 0,
        tax_rate: parseFloat(document.getElementById('materialTaxRate').value) || 0.01,
        freight: parseFloat(document.getElementById('materialFreight').value) || 0,
        default_supplier_id: document.getElementById('materialSupplier').value || null,
        inventory_min: parseFloat(document.getElementById('materialMin').value) || 0,
        inventory_max: parseFloat(document.getElementById('materialMax').value) || 0,
        remark: document.getElementById('materialRemark').value
    };

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
        alert('保存失败');
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
                <button class="btn btn-primary" onclick="printInquiryApproval(${i.id})">打印签字单</button>
                ${i.approval_status === '待审批' || i.approval_status === '材料员已审' ?
                    `<button class="btn btn-warning" onclick="approveInquiry(${i.id})">审批</button>` : ''}
            </td>
        </tr>
    `).join('');
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
            const details = data.details || [];
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
                    <table>
                        <thead><tr>
                            <th>材料</th><th>规格</th><th>供应商</th>
                            <th>库内价</th><th>本次报价</th><th>价差</th><th>最低价</th>
                        </tr></thead>
                        <tbody>
                            ${details.map(d => `
                                <tr>
                                    <td>${d.material_name}</td>
                                    <td>${d.specification || '-'}</td>
                                    <td>${d.supplier_name}</td>
                                    <td>¥${(d.library_price || 0).toFixed(2)}</td>
                                    <td>¥${(d.this_price || 0).toFixed(2)}</td>
                                    <td>¥${(d.price_diff || 0).toFixed(2)}</td>
                                    <td>${d.is_lowest == 1 ? '是' : '否'}</td>
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

async function approveInquiry(id) {
    const action = prompt('审批操作:\n1. 材料员审批\n2. 主管审批\n3. 驳回\n\n请输入数字:');
    if (!action) return;

    let act, remark = '';
    if (action === '1') act = 'material_clerk';
    else if (action === '2') act = 'manager';
    else if (action === '3') {
        act = 'reject';
        remark = prompt('请输入驳回原因:');
        if (!remark) return;
    } else {
        alert('无效操作');
        return;
    }

    try {
        const res = await fetch(`/api/purchase-inquiries/${id}/approve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: act, remark})
        });
        const data = await res.json();
        if (data.success) {
            alert('审批成功');
            loadInquiries();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('审批失败');
    }
}

async function printInquiryApproval(id) {
    window.open(`/api/purchase-inquiries/${id}/approval-print`, '_blank');
}

// ==================== 集采订单 ====================

async function loadOrders() {
    try {
        const res = await fetch('/api/purchase-orders');
        const data = await res.json();
        if (data.success) {
            renderOrdersTable(data.data);
        }
    } catch (e) {
        alert('加载订单失败');
    }
}

function renderOrdersTable(orders) {
    const tbody = document.getElementById('orderTable');
    tbody.innerHTML = orders.map(o => `
        <tr>
            <td>${o.order_no}</td>
            <td>${o.order_type}</td>
            <td>${o.supplier_name || '-'}</td>
            <td>¥${(o.total_amount || 0).toFixed(2)}</td>
            <td><span class="status ${getStatusClass(o.purchase_status)}">${o.purchase_status}</span></td>
            <td><span class="status ${getStatusClass(o.approval_status)}">${o.approval_status}</span></td>
            <td>
                <button class="btn btn-secondary" onclick="viewOrder(${o.id})">查看</button>
                <button class="btn btn-primary" onclick="printOrderApproval(${o.id})">打印签字单</button>
                ${o.approval_status === '待审批' || o.approval_status === '材料员已审' ?
                    `<button class="btn btn-warning" onclick="approveOrder(${o.id})">审批</button>` : ''}
            </td>
        </tr>
    `).join('');
}

async function viewOrder(id) {
    try {
        const res = await fetch(`/api/purchase-orders/${id}`);
        const data = await res.json();
        if (data.success) {
            const o = data.data;
            const details = data.details || [];
            document.getElementById('detailTitle').textContent = `订单详情 - ${o.order_no}`;
            document.getElementById('detailContent').innerHTML = `
                <div class="card">
                    <p><strong>单号:</strong> ${o.order_no}</p>
                    <p><strong>类型:</strong> ${o.order_type}</p>
                    <p><strong>供应商:</strong> ${o.supplier_name || '-'}</p>
                    <p><strong>总金额:</strong> ¥${(o.total_amount || 0).toFixed(2)}</p>
                    <p><strong>采购状态:</strong> <span class="status ${getStatusClass(o.purchase_status)}">${o.purchase_status}</span></p>
                    <p><strong>审批状态:</strong> <span class="status ${getStatusClass(o.approval_status)}">${o.approval_status}</span></p>
                    <p><strong>申请人:</strong> ${o.applicant_name || '-'}</p>
                    <p><strong>备注:</strong> ${o.remark || '-'}</p>
                </div>
                <h4 style="margin:15px 0;">订单明细</h4>
                <div class="table-container">
                    <table>
                        <thead><tr>
                            <th>材料编码</th><th>材料名称</th><th>规格</th>
                            <th>单位</th><th>单价</th><th>数量</th><th>金额</th>
                        </tr></thead>
                        <tbody>
                            ${details.map(d => `
                                <tr>
                                    <td>${d.material_code}</td>
                                    <td>${d.material_name}</td>
                                    <td>${d.specification || '-'}</td>
                                    <td>${d.unit_name || '-'}</td>
                                    <td>¥${(d.unit_price || 0).toFixed(2)}</td>
                                    <td>${d.quantity}</td>
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

async function approveOrder(id) {
    const action = prompt('审批操作:\n1. 材料员审批\n2. 主管审批\n3. 驳回\n\n请输入数字:');
    if (!action) return;

    let act, remark = '';
    if (action === '1') act = 'material_clerk';
    else if (action === '2') act = 'manager';
    else if (action === '3') {
        act = 'reject';
        remark = prompt('请输入驳回原因:');
        if (!remark) return;
    } else {
        alert('无效操作');
        return;
    }

    try {
        const res = await fetch(`/api/purchase-orders/${id}/approve`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: act, remark})
        });
        const data = await res.json();
        if (data.success) {
            alert('审批成功');
            loadOrders();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('审批失败');
    }
}

async function printOrderApproval(id) {
    window.open(`/api/purchase-orders/${id}/approval-print`, '_blank');
}

// 打开订单模态框
async function openOrderModal() {
    await loadUnitsAndSuppliers();  // loadUnitsAndSuppliers already loads first 500 materials
    orderDetails = [];
    renderOrderDetails();
    openModal('modal-order');
}

let orderDetails = [];

function addOrderDetail() {
    orderDetails.push({
        material_id: '',
        unit_price: 0,
        quantity: 1
    });
    renderOrderDetails();
}

function renderOrderDetails() {
    const tbody = document.getElementById('orderDetails');
    tbody.innerHTML = orderDetails.map((d, i) => `
        <tr>
            <td>
                <select onchange="updateOrderDetail(${i}, 'material_id', this.value)">
                    <option value="">--请选择--</option>
                    ${materials.map(m => `<option value="${m.id}" ${d.material_id == m.id ? 'selected' : ''}>${m.material_code} - ${m.material_name}</option>`).join('')}
                </select>
            </td>
            <td><input type="number" step="0.01" value="${d.unit_price}" onchange="updateOrderDetail(${i}, 'unit_price', this.value)"></td>
            <td><input type="number" step="0.01" value="${d.quantity}" onchange="updateOrderDetail(${i}, 'quantity', this.value)"></td>
            <td>¥${((d.unit_price || 0) * (d.quantity || 0)).toFixed(2)}</td>
            <td><button class="btn btn-danger" onclick="removeOrderDetail(${i})">删除</button></td>
        </tr>
    `).join('');
    updateOrderTotal();
}

function updateOrderDetail(index, field, value) {
    if (field === 'material_id') {
        const m = materials.find(x => x.id == value);
        orderDetails[index].material_id = value;
        orderDetails[index].unit_price = m ? m.tax_price : 0;
    } else {
        orderDetails[index][field] = parseFloat(value) || 0;
    }
    renderOrderDetails();
}

function removeOrderDetail(index) {
    orderDetails.splice(index, 1);
    renderOrderDetails();
}

function updateOrderTotal() {
    const total = orderDetails.reduce((sum, d) => sum + (d.unit_price || 0) * (d.quantity || 0), 0);
    document.getElementById('orderTotal').textContent = total.toFixed(2);
}

document.getElementById('orderForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const validDetails = orderDetails.filter(d => d.material_id && d.unit_price > 0);
    if (validDetails.length === 0) {
        alert('请添加有效的订单明细');
        return;
    }

    const body = {
        order_type: document.getElementById('orderType').value,
        supplier_id: document.getElementById('orderSupplier').value || null,
        remark: document.getElementById('orderRemark').value,
        details: validDetails.map(d => ({
            material_id: parseInt(d.material_id),
            unit_price: parseFloat(d.unit_price),
            quantity: parseFloat(d.quantity) || 1
        }))
    };

    try {
        const res = await fetch('/api/purchase-orders', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            alert(`订单创建成功！\n单号: ${data.order_no}`);
            closeModal('modal-order');
            orderDetails = [];
            loadOrders();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('创建失败');
    }
});

// ==================== 入库管理 ====================

async function loadStockIn() {
    try {
        const res = await fetch('/api/stock-in');
        const data = await res.json();
        if (data.success) {
            renderStockInTable(data.data);
        }
    } catch (e) {
        alert('加载入库单失败');
    }
}

function renderStockInTable(stockIn) {
    const tbody = document.getElementById('stockInTable');
    tbody.innerHTML = stockIn.map(s => `
        <tr>
            <td>${s.order_no}</td>
            <td>${s.source_type}</td>
            <td>${s.supplier_name || '-'}</td>
            <td>${s.warehouse_name || '-'}</td>
            <td>${s.in_time || '-'}</td>
            <td><span class="status approved">${s.status}</span></td>
        </tr>
    `).join('');
}

// ==================== 出库管理 ====================

async function loadStockOut() {
    try {
        const res = await fetch('/api/stock-out');
        const data = await res.json();
        if (data.success) {
            renderStockOutTable(data.data);
        }
    } catch (e) {
        alert('加载出库单失败');
    }
}

function renderStockOutTable(stockOut) {
    const tbody = document.getElementById('stockOutTable');
    tbody.innerHTML = (stockOut || []).map(s => `
        <tr>
            <td>${s.order_no}</td>
            <td>${s.out_type}</td>
            <td>${s.customer_name || '-'}</td>
            <td>${s.out_time || '-'}</td>
            <td>${s.operator_name || '-'}</td>
        </tr>
    `).join('') || '<tr><td colspan="5" class="loading">暂无数据</td></tr>';
}

// ==================== 库存管理 ====================

async function loadInventory() {
    try {
        const res = await fetch('/api/inventory');
        const data = await res.json();
        if (data.success) {
            renderInventoryTable(data.data);
        }
    } catch (e) {
        alert('加载库存失败');
    }
}

function renderInventoryTable(inventory) {
    const tbody = document.getElementById('inventoryTable');
    tbody.innerHTML = (inventory || []).map(i => `
        <tr>
            <td>${i.material_code || '-'}</td>
            <td>${i.material_name || '-'}</td>
            <td>${i.specification || '-'}</td>
            <td>${i.warehouse_name || '-'}</td>
            <td>${i.quantity || 0}</td>
            <td>¥${(i.unit_price || 0).toFixed(2)}</td>
            <td>¥${((i.quantity || 0) * (i.unit_price || 0)).toFixed(2)}</td>
        </tr>
    `).join('') || '<tr><td colspan="7" class="loading">暂无数据</td></tr>';
}

// ==================== 供应商管理 ====================

async function loadSuppliers() {
    try {
        const res = await fetch('/api/suppliers');
        const data = await res.json();
        if (data.success) {
            suppliers = data.data;
            renderSupplierTable();
        }
    } catch (e) {
        alert('加载供应商失败');
    }
}

function renderSupplierTable() {
    const tbody = document.getElementById('supplierTable');
    tbody.innerHTML = suppliers.map(s => `
        <tr>
            <td>${s.supplier_name}</td>
            <td>${s.contact || '-'}</td>
            <td>${s.phone || '-'}</td>
            <td>${s.address || '-'}</td>
            <td><button class="btn btn-danger" onclick="deleteSupplier(${s.id})">删除</button></td>
        </tr>
    `).join('');
}

async function deleteSupplier(id) {
    if (!confirm('确定要删除该供应商吗？')) return;
    alert('功能开发中');
}

document.getElementById('supplierForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = {
        supplier_name: document.getElementById('supplierName').value,
        contact: document.getElementById('supplierContact').value,
        phone: document.getElementById('supplierPhone').value,
        address: document.getElementById('supplierAddress').value
    };

    try {
        const res = await fetch('/api/suppliers', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            alert('创建成功');
            closeModal('modal-supplier');
            loadSuppliers();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('创建失败');
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
    tbody.innerHTML = (statements || []).map(s => `
        <tr>
            <td>${s.statement_no}</td>
            <td>${s.supplier_name || s.customer_name || '-'}</td>
            <td>${s.period_start || '-'} ~ ${s.period_end || '-'}</td>
            <td>¥${(s.total_amount || 0).toFixed(2)}</td>
            <td><span class="status ${s.status === '已确认' ? 'approved' : s.status === '已打印' ? 'completed' : 'pending'}">${s.status}</span></td>
            <td>
                <button class="btn btn-secondary" onclick="viewReconciliation(${s.id})">查看</button>
                <button class="btn btn-primary" onclick="printReconciliation(${s.id})">打印</button>
            </td>
        </tr>
    `).join('') || '<tr><td colspan="6" class="loading">暂无数据</td></tr>';
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
        // 先加载单位、供应商（走缓存，小数据字典）
        const [unitsCached, supCached] = await Promise.all([
            loadCacheOrFetch('dict_units', '/api/units'),
            loadCacheOrFetch('dict_suppliers', '/api/suppliers')
        ]);

        units = unitsCached.success ? unitsCached.data : [];
        suppliers = supCached.success ? supCached.data : [];

        // 单独加载材料（不走缓存，确保获取最新数据）
        let matData = { success: false, data: [] };
        try {
            const matRes = await fetch('/api/materials?page=1&page_size=2000');
            matData = await matRes.json();
        } catch (e) {
            console.error('加载材料失败', e);
        }
        if (matData.success && matData.data) {
            materials = matData.data;
        }

        // 填充单位下拉框
        const unitSelect = document.getElementById('materialUnit');
        if (unitSelect) {
            unitSelect.innerHTML = '<option value="">--请选择--</option>' + units.map(u => `<option value="${u.id}">${u.unit_name}</option>`).join('');
        }

        // 填充供应商下拉框
        const supSelect = document.getElementById('materialSupplier');
        if (supSelect) {
            supSelect.innerHTML = '<option value="">--请选择--</option>' + suppliers.map(s => `<option value="${s.id}">${s.supplier_name}</option>`).join('');
        }

        const stockInSup = document.getElementById('stockInSupplier');
        if (stockInSup) {
            stockInSup.innerHTML = '<option value="">--请选择--</option>' + suppliers.map(s => `<option value="${s.id}">${s.supplier_name}</option>`).join('');
        }

        const orderSup = document.getElementById('orderSupplier');
        if (orderSup) {
            orderSup.innerHTML = '<option value="">--请选择--</option>' + suppliers.map(s => `<option value="${s.id}">${s.supplier_name}</option>`).join('');
        }

    } catch (e) {
        console.error('加载下拉数据失败', e);
    }
}

// ==================== 询价单明细操作 ====================

function addInquiryDetail() {
    inquiryDetails.push({
        material_id: '',
        supplier_id: '',
        library_price: 0,
        this_price: 0,
        quantity: 1
    });
    renderInquiryDetails();
}

function renderInquiryDetails() {
    const tbody = document.getElementById('inquiryDetails');
    tbody.innerHTML = inquiryDetails.map((d, i) => `
        <tr>
            <td>
                <select onchange="updateInquiryDetail(${i}, 'material_id', this.value)">
                    <option value="">--请选择--</option>
                    ${materials.map(m => `<option value="${m.id}" ${d.material_id == m.id ? 'selected' : ''}>${m.material_code} - ${m.material_name}</option>`).join('')}
                </select>
            </td>
            <td>
                <select onchange="updateInquiryDetail(${i}, 'supplier_id', this.value)">
                    <option value="">--请选择--</option>
                    ${suppliers.map(s => `<option value="${s.id}" ${d.supplier_id == s.id ? 'selected' : ''}>${s.supplier_name}</option>`).join('')}
                </select>
            </td>
            <td><input type="number" step="0.01" value="${d.library_price}" readonly></td>
            <td><input type="number" step="0.01" value="${d.this_price}" onchange="updateInquiryDetail(${i}, 'this_price', this.value)"></td>
            <td><input type="number" step="0.01" value="${d.quantity}" onchange="updateInquiryDetail(${i}, 'quantity', this.value)"></td>
            <td><button class="btn btn-danger" onclick="removeInquiryDetail(${i})">删除</button></td>
        </tr>
    `).join('');
    updateInquiryTotal();
}

function updateInquiryDetail(index, field, value) {
    if (field === 'material_id') {
        const m = materials.find(x => x.id == value);
        inquiryDetails[index].material_id = value;
        inquiryDetails[index].library_price = m ? m.tax_price : 0;
    } else if (field === 'this_price' || field === 'quantity') {
        inquiryDetails[index][field] = parseFloat(value) || 0;
    } else {
        inquiryDetails[index][field] = value;
    }
    renderInquiryDetails();
}

function removeInquiryDetail(index) {
    inquiryDetails.splice(index, 1);
    renderInquiryDetails();
}

function updateInquiryTotal() {
    const total = inquiryDetails.reduce((sum, d) => sum + (d.this_price || 0) * (d.quantity || 0), 0);
    document.getElementById('inquiryTotal').textContent = total.toFixed(2);
}

document.getElementById('inquiryForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const validDetails = inquiryDetails.filter(d => d.material_id && d.supplier_id && d.this_price > 0);
    if (validDetails.length === 0) {
        alert('请添加有效的询价明细');
        return;
    }

    const body = {
        inquiry_date: document.getElementById('inquiryDate').value,
        remark: document.getElementById('inquiryRemark').value,
        details: validDetails.map(d => ({
            material_id: parseInt(d.material_id),
            supplier_id: parseInt(d.supplier_id),
            this_price: parseFloat(d.this_price),
            library_price: parseFloat(d.library_price),
            quantity: parseFloat(d.quantity) || 1
        }))
    };

    try {
        const res = await fetch('/api/purchase-inquiries', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        const data = await res.json();
        if (data.success) {
            alert(`询价单创建成功！\n单号: ${data.inquiry_no}`);
            closeModal('modal-inquiry');
            inquiryDetails = [];
            loadInquiries();
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert('创建失败');
    }
});

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
        loadUnitsAndSuppliers().then(() => {
            if (inquiryDetails.length === 0) {
                addInquiryDetail();
            }
        });
        modal.dataset.loaded = 'true';
    }
    // 打开入库单模态框时加载数据
    if (id === 'modal-stock-in' && !modal.dataset.loaded) {
        loadUnitsAndSuppliers();
        modal.dataset.loaded = 'true';
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
    tbody.innerHTML = allUsers.map(u => `
        <tr>
            <td>${u.id}</td>
            <td>${u.username}</td>
            <td>${u.real_name}</td>
            <td>${u.role_name || '-'}</td>
            <td><span class="status ${u.is_active ? 'approved' : 'rejected'}">${u.is_active ? '启用' : '禁用'}</span></td>
            <td>
                <button class="btn btn-secondary" onclick="editUser(${u.id})">编辑</button>
                ${u.id !== 1 ? `<button class="btn btn-danger" onclick="deleteUser(${u.id})">删除</button>` : ''}
            </td>
        </tr>
    `).join('');
}

async function editUser(id) {
    const u = allUsers.find(x => x.id === id);
    if (!u) return;

    await loadRolesToSelect();

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

document.getElementById('userForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const id = document.getElementById('userId').value;
    const body = {
        username: document.getElementById('userUsername').value,
        real_name: document.getElementById('userRealName').value,
        role_id: document.getElementById('userRole').value || null,
        is_active: parseInt(document.getElementById('userActive').value)
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
