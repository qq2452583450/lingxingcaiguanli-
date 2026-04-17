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
    """获取所有用户"""
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

@system_bp.route('/suppliers', methods=['GET'])
def get_suppliers():
    """获取所有供应商"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suppliers ORDER BY supplier_name")
    suppliers = [dict(row) for row in cursor.fetchall()]
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

    cursor.execute("""
        INSERT INTO suppliers (supplier_name, contact, phone, address, remark, create_time)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (escape(data.get('supplier_name', '')), escape(data.get('contact', '')),
          escape(data.get('phone', '')), escape(data.get('address', '')),
          escape(data.get('remark', '')), now))
    supplier_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': supplier_id})


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
    """获取所有项目"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.*, c.customer_name
        FROM projects p
        LEFT JOIN customers c ON p.customer_id = c.id
        ORDER BY p.create_time DESC
    """)
    projects = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': projects})
