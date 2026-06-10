"""
系统设置蓝图（用户/角色/供应商/客户/单位/项目）
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime
from helpers import hash_password, get_db
from html import escape

system_bp = Blueprint('system', __name__, url_prefix='/api')


# ==================== 用户管理 ====================

@system_bp.route('/users', methods=['GET'])
def get_users():
    """获取所有用户（含绑定项目）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.username, u.real_name, u.role_id, u.is_active, u.create_time,
               r.role_name
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.id
        ORDER BY u.id
    """)
    users = [dict(row) for row in cursor.fetchall()]

    # 查询每个用户绑定的项目
    for u in users:
        cursor.execute("""
            SELECT p.id, p.project_name, p.project_code
            FROM user_projects up
            JOIN projects p ON up.project_id = p.id
            WHERE up.user_id = ?
            ORDER BY p.project_name
        """, (u['id'],))
        u['projects'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return jsonify({'success': True, 'data': users})


@system_bp.route('/users', methods=['POST'])
def create_user():
    """创建用户"""
    data = request.json
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    # 仅管理员可创建用户
    if user.get('role_name') != '系统管理员':
        return jsonify({'success': False, 'message': '仅管理员可创建用户'})

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 检查用户名是否已存在
    cursor.execute("SELECT id FROM users WHERE username = ?", (data.get('username'),))
    if cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': '用户名已存在'})

    # 密码哈希
    password = data.get('password', '888888')
    hashed = hash_password(password)

    try:
        cursor.execute("""
            INSERT INTO users (username, password, real_name, role_id, is_active, create_time)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            escape(data.get('username', '')), hashed, escape(data.get('real_name', '')),
            data.get('role_id'), data.get('is_active', 1), now
        ))
        user_id = cursor.lastrowid

        # 绑定项目
        project_ids = data.get('project_ids', [])
        for pid in project_ids:
            cursor.execute("INSERT OR IGNORE INTO user_projects (user_id, project_id) VALUES (?, ?)", (user_id, int(pid)))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': user_id})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': str(e)})


@system_bp.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """更新用户"""
    data = request.json
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})
    if user.get('role_name') != '系统管理员':
        return jsonify({'success': False, 'message': '仅管理员可修改用户'})

    conn = get_db()
    cursor = conn.cursor()

    password = data.get('password')
    if password:
        hashed = hash_password(password)
        cursor.execute("""
            UPDATE users SET username = ?, real_name = ?, role_id = ?,
            is_active = ?, password = ? WHERE id = ?
        """, (escape(data.get('username', '')), escape(data.get('real_name', '')), data.get('role_id'),
              data.get('is_active', 1), hashed, user_id))
    else:
        cursor.execute("""
            UPDATE users SET username = ?, real_name = ?, role_id = ?,
            is_active = ? WHERE id = ?
        """, (escape(data.get('username', '')), escape(data.get('real_name', '')), data.get('role_id'),
              data.get('is_active', 1), user_id))

    # 更新项目绑定
    project_ids = data.get('project_ids', None)
    if project_ids is not None:
        cursor.execute("DELETE FROM user_projects WHERE user_id = ?", (user_id,))
        for pid in project_ids:
            cursor.execute("INSERT OR IGNORE INTO user_projects (user_id, project_id) VALUES (?, ?)", (user_id, int(pid)))

    conn.commit()
    conn.close()
    return jsonify({'success': True})


@system_bp.route('/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """删除用户"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})
    if user.get('role_name') != '系统管理员':
        return jsonify({'success': False, 'message': '仅管理员可删除用户'})

    conn = get_db()
    cursor = conn.cursor()

    if user_id == 1:
        conn.close()
        return jsonify({'success': False, 'message': '不能删除管理员账号'})

    cursor.execute("DELETE FROM user_projects WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ==================== 角色管理 ====================

@system_bp.route('/roles', methods=['GET'])
def get_roles():
    """获取所有角色"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM roles ORDER BY id")
    roles = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': roles})


# ==================== 供应商管理 ====================

def _get_or_create_role(cursor, role_name):
    cursor.execute("SELECT id FROM roles WHERE role_name = ?", (role_name,))
    row = cursor.fetchone()
    if row:
        return row['id'] if hasattr(row, 'keys') else row[0]
    cursor.execute("INSERT INTO roles (role_name, permissions) VALUES (?, ?)", (role_name, ''))
    return cursor.lastrowid


def _ensure_supplier_user_account(cursor, supplier, now=None):
    if supplier.get('user_id') and supplier.get('account_username'):
        return supplier['user_id'], supplier['account_username'], False

    now = now or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    supplier_id = supplier['id']
    supplier_name = supplier.get('supplier_name') or f'供应商{supplier_id}'
    username = f'supplier_{supplier_id:05d}'
    role_id = _get_or_create_role(cursor, '供应商')

    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    user_row = cursor.fetchone()
    if user_row:
        user_id = user_row['id'] if hasattr(user_row, 'keys') else user_row[0]
        cursor.execute("""
            UPDATE users
            SET real_name = ?, role_id = ?, is_active = 1, must_change_password = 1
            WHERE id = ?
        """, (supplier_name, role_id, user_id))
    else:
        cursor.execute("""
            INSERT INTO users (
                username, password, real_name, role_id, is_active, create_time, must_change_password
            ) VALUES (?, ?, ?, ?, 1, ?, 1)
        """, (username, hash_password('888888'), supplier_name, role_id, now))
        user_id = cursor.lastrowid

    cursor.execute("UPDATE suppliers SET user_id = ? WHERE id = ?", (user_id, supplier_id))
    return user_id, username, True


@system_bp.route('/suppliers', methods=['GET'])
def get_suppliers():
    """获取所有供应商"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, u.username AS account_username
        FROM suppliers s
        LEFT JOIN users u ON s.user_id = u.id
        ORDER BY s.supplier_name
    """)
    suppliers = [dict(row) for row in cursor.fetchall()]
    changed = False
    for supplier in suppliers:
        _user_id, username, created = _ensure_supplier_user_account(cursor, supplier)
        if created:
            supplier['user_id'] = _user_id
            supplier['account_username'] = username
            changed = True
    if changed:
        conn.commit()
    conn.close()
    return jsonify({'success': True, 'data': suppliers})


@system_bp.route('/suppliers', methods=['POST'])
def create_supplier():
    """创建供应商"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    supplier_name = escape(data.get('supplier_name', '').strip())
    if not supplier_name:
        conn.close()
        return jsonify({'success': False, 'message': '供应商名称不能为空'})

    try:
        cursor.execute("""
            INSERT INTO suppliers (supplier_name, business_scope, contact, phone, address, remark, tax_rate, create_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (supplier_name, escape(data.get('business_scope', '')),
              escape(data.get('contact', '')), escape(data.get('phone', '')),
              escape(data.get('address', '')), escape(data.get('remark', '')),
              data.get('tax_rate'), now))
        supplier_id = cursor.lastrowid

        role_id = _get_or_create_role(cursor, '供应商')
        username = f'supplier_{supplier_id:05d}'
        cursor.execute("""
            INSERT INTO users (
                username, password, real_name, role_id, is_active, create_time, must_change_password
            ) VALUES (?, ?, ?, ?, 1, ?, 1)
        """, (username, hash_password('888888'), supplier_name, role_id, now))
        supplier_user_id = cursor.lastrowid
        cursor.execute("UPDATE suppliers SET user_id = ? WHERE id = ?", (supplier_user_id, supplier_id))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': supplier_id, 'username': username})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': str(e)})


@system_bp.route('/suppliers/<int:supplier_id>', methods=['PUT'])
def update_supplier(supplier_id):
    """更新供应商"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})
    if user.get('role_name') not in ('系统管理员', '材料员'):
        return jsonify({'success': False, 'message': '无权限'})

    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    supplier_name = escape(data.get('supplier_name', ''))
    cursor.execute("""
        UPDATE suppliers SET supplier_name = ?, business_scope = ?, contact = ?, phone = ?, address = ?, remark = ?, tax_rate = ?
        WHERE id = ?
    """, (supplier_name, escape(data.get('business_scope', '')),
          escape(data.get('contact', '')), escape(data.get('phone', '')),
          escape(data.get('address', '')), escape(data.get('remark', '')),
          data.get('tax_rate'), supplier_id))
    cursor.execute("SELECT user_id FROM suppliers WHERE id = ?", (supplier_id,))
    supplier = cursor.fetchone()
    if supplier and supplier['user_id']:
        cursor.execute("UPDATE users SET real_name = ? WHERE id = ?", (supplier_name, supplier['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@system_bp.route('/suppliers/<int:supplier_id>', methods=['DELETE'])
def delete_supplier(supplier_id):
    """删除供应商"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM materials WHERE default_supplier_id = ?", (supplier_id,))
    if cursor.fetchone()[0] > 0:
        conn.close()
        return jsonify({'success': False, 'message': '该供应商已被材料引用，无法删除'})

    cursor.execute("SELECT COUNT(*) FROM purchase_inquiry_quotes WHERE supplier_id = ?", (supplier_id,))
    if cursor.fetchone()[0] > 0:
        conn.close()
        return jsonify({'success': False, 'message': '该供应商已有报价记录，无法删除'})

    cursor.execute("SELECT user_id FROM suppliers WHERE id = ?", (supplier_id,))
    supplier = cursor.fetchone()
    cursor.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
    if supplier and supplier['user_id']:
        cursor.execute("DELETE FROM users WHERE id = ?", (supplier['user_id'],))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ==================== 客户管理 ====================

@system_bp.route('/customers', methods=['GET'])
def get_customers():
    """获取所有客户"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customers ORDER BY customer_name")
    customers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': customers})


@system_bp.route('/customers', methods=['POST'])
def create_customer():
    """创建客户"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 生成客户编码
    cursor.execute("SELECT MAX(CAST(SUBSTR(customer_code, 4) AS INTEGER)) FROM customers WHERE customer_code LIKE 'KH-%'")
    max_code = cursor.fetchone()[0] or 0
    customer_code = f'KH-{str(max_code + 1).zfill(4)}'

    cursor.execute("""
        INSERT INTO customers (customer_code, customer_name, address, phone, contact, initial_balance, remark, create_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (customer_code, escape(data.get('customer_name', '')), escape(data.get('address', '')),
          escape(data.get('phone', '')), escape(data.get('contact', '')),
          data.get('initial_balance', 0), escape(data.get('remark', '')), now))
    customer_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': customer_id, 'customer_code': customer_code})


# ==================== 单位管理 ====================

@system_bp.route('/units', methods=['GET'])
def get_units():
    """获取所有单位"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM units ORDER BY unit_name")
    units = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': units})


# ==================== 项目管理 ====================

@system_bp.route('/projects', methods=['GET'])
def get_projects():
    """获取项目列表，支持 ?mine=1 只返回当前用户绑定的项目"""
    conn = get_db()
    cursor = conn.cursor()

    mine = request.args.get('mine', '0') == '1'
    user = session.get('user')

    if mine and user:
        # 只返回当前用户绑定的项目
        cursor.execute("""
            SELECT p.*, c.customer_name
            FROM projects p
            LEFT JOIN customers c ON p.customer_id = c.id
            JOIN user_projects up ON p.id = up.project_id
            WHERE up.user_id = ?
            ORDER BY p.create_time DESC
        """, (user['id'],))
    else:
        cursor.execute("""
            SELECT p.*, c.customer_name
            FROM projects p
            LEFT JOIN customers c ON p.customer_id = c.id
            ORDER BY p.create_time DESC
        """)

    projects = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': projects})


@system_bp.route('/projects', methods=['POST'])
def create_project():
    """创建项目"""
    data = request.json
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 检查编号是否重复
    project_code = data.get('project_code', '').strip()
    if not project_code:
        # 自动生成编号
        cursor.execute("SELECT MAX(CAST(SUBSTR(project_code, 4) AS INTEGER)) FROM projects WHERE project_code LIKE 'XM-%'")
        max_code = cursor.fetchone()[0] or 0
        project_code = f'XM-{str(max_code + 1).zfill(4)}'
    else:
        cursor.execute("SELECT id FROM projects WHERE project_code = ?", (project_code,))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': '项目编号已存在'})

    project_name = data.get('project_name', '').strip()
    if not project_name:
        conn.close()
        return jsonify({'success': False, 'message': '项目名称不能为空'})

    try:
        cursor.execute("""
            INSERT INTO projects (project_code, project_name, contract_no, customer_id, start_date, end_date, remark, create_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_code, escape(project_name), escape(data.get('contract_no', '')),
              data.get('customer_id') or None, data.get('start_date') or None,
              data.get('end_date') or None, escape(data.get('remark', '')), now))
        project_id = cursor.lastrowid

        # 自动给admin用户(user_id=1)绑定新项目
        cursor.execute("INSERT INTO user_projects (user_id, project_id) VALUES (1, ?)", (project_id,))

        # 也给创建者绑定
        if user['id'] != 1:
            cursor.execute("INSERT OR IGNORE INTO user_projects (user_id, project_id) VALUES (?, ?)", (user['id'], project_id))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id': project_id, 'project_code': project_code})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': str(e)})


@system_bp.route('/projects/<int:project_id>', methods=['PUT'])
def update_project(project_id):
    """更新项目"""
    data = request.json
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()

    project_code = data.get('project_code', '').strip()
    if project_code:
        cursor.execute("SELECT id FROM projects WHERE project_code = ? AND id != ?", (project_code, project_id))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': '项目编号已存在'})

    try:
        cursor.execute("""
            UPDATE projects SET project_code = ?, project_name = ?, contract_no = ?,
            customer_id = ?, start_date = ?, end_date = ?, remark = ?
            WHERE id = ?
        """, (escape(project_code), escape(data.get('project_name', '')),
              escape(data.get('contract_no', '')), data.get('customer_id') or None,
              data.get('start_date') or None, data.get('end_date') or None,
              escape(data.get('remark', '')), project_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': str(e)})


@system_bp.route('/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    """删除项目"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()

    # 检查是否有关联数据
    cursor.execute("SELECT COUNT(*) FROM user_projects WHERE project_id = ?", (project_id,))
    if cursor.fetchone()[0] > 0:
        cursor.execute("DELETE FROM user_projects WHERE project_id = ?", (project_id,))

    cursor.execute("SELECT COUNT(*) FROM reconciliation_statements WHERE project_id = ?", (project_id,))
    recon_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM purchase_orders WHERE project_id = ?", (project_id,))
    order_count = cursor.fetchone()[0]

    if recon_count > 0 or order_count > 0:
        conn.close()
        return jsonify({'success': False, 'message': f'该项目已关联对账单({recon_count}条)或采购单({order_count}条)，无法删除'})

    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})
