"""
供应商门户蓝图 — 注册、登录、报价
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime
from helpers import hash_password, verify_password, get_db
from html import escape
import threading

supplier_bp = Blueprint('supplier_portal', __name__, url_prefix='/api/supplier')

# 登录尝试追踪
_login_attempts = {}
_attempts_lock = threading.Lock()
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _check_rate_limit(key):
    with _attempts_lock:
        if key in _login_attempts:
            attempts, lock_until = _login_attempts[key]
            if attempts >= MAX_ATTEMPTS:
                if datetime.now() < lock_until:
                    remaining = (lock_until - datetime.now()).seconds // 60 + 1
                    return False, remaining
                else:
                    del _login_attempts[key]
        return True, 0


def _record_failed_attempt(key):
    with _attempts_lock:
        if key not in _login_attempts:
            _login_attempts[key] = (1, None)
        else:
            attempts, _ = _login_attempts[key]
            if attempts + 1 >= MAX_ATTEMPTS:
                lock_until = datetime.now() + __import__('datetime').timedelta(minutes=LOCKOUT_MINUTES)
                _login_attempts[key] = (MAX_ATTEMPTS, lock_until)
            else:
                _login_attempts[key] = (attempts + 1, None)


def _reset_attempts(key):
    with _attempts_lock:
        _login_attempts.pop(key, None)


def _current_supplier():
    """获取当前登录的供应商用户信息"""
    return session.get('supplier_user')


# ==================== 注册 ====================

@supplier_bp.route('/register', methods=['POST'])
def register():
    """供应商注册"""
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    supplier_name = (data.get('supplier_name') or '').strip()
    contact = (data.get('contact') or '').strip()
    phone = (data.get('phone') or '').strip()
    address = (data.get('address') or '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': '请填写登录账号和密码'})
    if len(password) < 6:
        return jsonify({'success': False, 'message': '密码至少6位'})
    if not supplier_name:
        return jsonify({'success': False, 'message': '请填写供应商名称'})

    conn = get_db()
    cursor = conn.cursor()

    # 检查账号是否已存在
    cursor.execute("SELECT id FROM supplier_accounts WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'message': '该登录账号已被使用'})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 创建供应商记录
    cursor.execute("""
        INSERT INTO suppliers (supplier_name, contact, phone, address, create_time)
        VALUES (?, ?, ?, ?, ?)
    """, (escape(supplier_name), escape(contact), escape(phone), escape(address), now))
    supplier_id = cursor.lastrowid

    # 创建供应商账号（默认待审核）
    cursor.execute("""
        INSERT INTO supplier_accounts (supplier_id, username, password, status, is_active, create_time)
        VALUES (?, ?, ?, 'pending', 0, ?)
    """, (supplier_id, username, hash_password(password), now))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': '注册成功，请等待管理员审核后登录'})


# ==================== 登录 ====================

@supplier_bp.route('/login', methods=['POST'])
def login():
    """供应商登录"""
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': '请填写账号和密码'})

    rate_key = f'supplier:{request.remote_addr}:{username}'
    allowed, remaining = _check_rate_limit(rate_key)
    if not allowed:
        return jsonify({'success': False, 'message': f'登录失败次数过多，请 {remaining} 分钟后再试'})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT sa.*, s.supplier_name
        FROM supplier_accounts sa
        JOIN suppliers s ON sa.supplier_id = s.id
        WHERE sa.username = ?
    """, (username,))
    row = cursor.fetchone()

    if not row:
        _record_failed_attempt(rate_key)
        conn.close()
        return jsonify({'success': False, 'message': '账号或密码错误'})

    account = dict(row)

    if account['status'] != 'active' or not account['is_active']:
        conn.close()
        return jsonify({'success': False, 'message': '账号未启用，请联系管理员'})

    password_needs_upgrade = False
    if verify_password(password, account['password']):
        password_ok = True
    elif account['password'] == password:
        password_ok = True
        password_needs_upgrade = True
    else:
        password_ok = False

    if not password_ok:
        _record_failed_attempt(rate_key)
        allowed, remaining = _check_rate_limit(rate_key)
        conn.close()
        if not allowed:
            return jsonify({'success': False, 'message': f'登录失败次数过多，请 {remaining} 分钟后再试'})
        return jsonify({'success': False, 'message': '账号或密码错误'})

    _reset_attempts(rate_key)

    # 更新最后登录时间
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if password_needs_upgrade:
        cursor.execute("UPDATE supplier_accounts SET password = ? WHERE id = ?",
                       (hash_password(password), account['id']))
    cursor.execute("UPDATE supplier_accounts SET last_login_time = ? WHERE id = ?", (now, account['id']))
    conn.commit()
    conn.close()

    supplier_user = {
        'account_id': account['id'],
        'supplier_id': account['supplier_id'],
        'username': account['username'],
        'supplier_name': account['supplier_name'],
        'profile_completed': account.get('profile_completed', 0),
    }
    session['supplier_user'] = supplier_user

    return jsonify({'success': True, 'user': supplier_user})


# ==================== 登出 ====================

@supplier_bp.route('/logout', methods=['POST'])
def logout():
    """供应商登出"""
    session.pop('supplier_user', None)
    return jsonify({'success': True})


# ==================== 当前用户 ====================

@supplier_bp.route('/me', methods=['GET'])
def me():
    """获取当前供应商用户信息"""
    user = _current_supplier()
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    # 查询完整供应商信息
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.supplier_name, s.contact, s.phone, s.address, s.business_scope,
               sa.profile_completed
        FROM suppliers s
        JOIN supplier_accounts sa ON s.id = sa.supplier_id
        WHERE s.id = ?
    """, (user['supplier_id'],))
    row = cursor.fetchone()
    conn.close()

    profile = {}
    if row:
        profile = dict(row)
        user['profile_completed'] = profile.get('profile_completed', 0)

    return jsonify({'success': True, 'user': user, 'profile': profile})


# ==================== 完善资料 ====================

@supplier_bp.route('/profile', methods=['PUT'])
def update_profile():
    """供应商完善资料"""
    user = _current_supplier()
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    data = request.json or {}
    supplier_name = (data.get('supplier_name') or '').strip()
    contact = (data.get('contact') or '').strip()
    phone = (data.get('phone') or '').strip()
    address = (data.get('address') or '').strip()
    business_scope = (data.get('business_scope') or '').strip()
    password = (data.get('password') or '').strip()
    password2 = (data.get('password2') or '').strip()

    if not supplier_name:
        return jsonify({'success': False, 'message': '请填写供应商名称'})
    if not contact:
        return jsonify({'success': False, 'message': '请填写联系人'})
    if not phone:
        return jsonify({'success': False, 'message': '请填写手机号'})
    if not business_scope:
        return jsonify({'success': False, 'message': '请填写经营范围'})

    conn = get_db()
    cursor = conn.cursor()

    # 更新供应商信息
    cursor.execute("""
        UPDATE suppliers SET supplier_name = ?, contact = ?, phone = ?, address = ?, business_scope = ?
        WHERE id = ?
    """, (escape(supplier_name), escape(contact), escape(phone), escape(address),
          escape(business_scope), user['supplier_id']))

    # 如果填写了新密码，更新密码
    if password:
        if len(password) < 6:
            conn.close()
            return jsonify({'success': False, 'message': '密码至少6位'})
        if password != password2:
            conn.close()
            return jsonify({'success': False, 'message': '两次密码不一致'})
        cursor.execute("UPDATE supplier_accounts SET password = ? WHERE id = ?",
                       (hash_password(password), user['account_id']))

    # 标记资料已完善
    cursor.execute("UPDATE supplier_accounts SET profile_completed = 1 WHERE id = ?",
                   (user['account_id'],))

    conn.commit()
    conn.close()

    # 更新 session
    session['supplier_user']['supplier_name'] = supplier_name
    session['supplier_user']['profile_completed'] = 1

    return jsonify({'success': True, 'message': '资料已完善'})


# ==================== 报价任务列表 ====================

@supplier_bp.route('/quote-requests', methods=['GET'])
def get_quote_requests():
    """获取当前供应商的报价任务列表"""
    user = _current_supplier()
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT
            pi.id AS inquiry_id,
            pi.inquiry_no,
            pi.inquiry_date,
            pi.quote_status AS inquiry_quote_status,
            pi.quote_deadline,
            pi.remark AS inquiry_remark
        FROM purchase_inquiry_quotes piq
        JOIN purchase_inquiry_items pii ON piq.item_id = pii.id
        JOIN purchase_inquiries pi ON pii.inquiry_id = pi.id
        WHERE piq.supplier_id = ?
          AND pi.quote_status IN ('collecting', 'locked')
        ORDER BY pi.inquiry_date DESC, pi.id DESC
    """, (user['supplier_id'],))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({'success': True, 'data': rows})


# ==================== 报价任务详情 ====================

@supplier_bp.route('/quote-requests/<int:inquiry_id>', methods=['GET'])
def get_quote_request_detail(inquiry_id):
    """获取某个询比价单中当前供应商的报价明细"""
    user = _current_supplier()
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()

    # 确认该供应商确实被邀请了这个询比价（且已发布）
    cursor.execute("""
        SELECT pi.id, pi.inquiry_no, pi.inquiry_date, pi.quote_status, pi.quote_deadline, pi.remark
        FROM purchase_inquiries pi
        WHERE pi.id = ? AND pi.quote_status IN ('collecting', 'locked') AND EXISTS (
            SELECT 1 FROM purchase_inquiry_quotes piq
            JOIN purchase_inquiry_items pii ON piq.item_id = pii.id
            WHERE pii.inquiry_id = pi.id AND piq.supplier_id = ?
        )
    """, (inquiry_id, user['supplier_id']))
    inquiry = cursor.fetchone()
    if not inquiry:
        conn.close()
        return jsonify({'success': False, 'message': '未找到相关报价任务'})

    inquiry_data = dict(inquiry)

    # 获取该供应商的报价行（不返回其他供应商信息）
    cursor.execute("""
        SELECT piq.id AS quote_id, piq.item_id,
               piq.tax_price, piq.tax_exempt_price, piq.tax_rate,
               piq.total_amount, piq.quote_status, piq.submitted_at,
               piq.updated_at, piq.supplier_remark,
               pii.material_id, pii.quantity,
               m.material_name, m.specification, m.detail_spec,
               m.brand, m.is_national_standard,
               u.unit_name
        FROM purchase_inquiry_quotes piq
        JOIN purchase_inquiry_items pii ON piq.item_id = pii.id
        LEFT JOIN materials m ON pii.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        WHERE pii.inquiry_id = ? AND piq.supplier_id = ?
        ORDER BY pii.id
    """, (inquiry_id, user['supplier_id']))
    quotes = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({'success': True, 'inquiry': inquiry_data, 'quotes': quotes})


# ==================== 保存报价 ====================

@supplier_bp.route('/quotes/<int:quote_id>', methods=['PUT'])
def save_quote(quote_id):
    """保存报价（草稿）"""
    user = _current_supplier()
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    data = request.json or {}
    tax_price = data.get('tax_price')
    tax_rate = data.get('tax_rate', 0.13)
    supplier_remark = (data.get('supplier_remark') or '').strip()

    if tax_price is not None:
        try:
            tax_price = float(tax_price)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': '请填写有效的含税单价'})
        if tax_price < 0:
            return jsonify({'success': False, 'message': '含税单价不能为负数'})

    conn = get_db()
    cursor = conn.cursor()

    # 验证该报价属于当前供应商且可编辑
    cursor.execute("""
        SELECT piq.id, piq.quote_status AS q_status, pi.quote_status AS inquiry_quote_status,
               pi.quote_deadline, pii.quantity
        FROM purchase_inquiry_quotes piq
        JOIN purchase_inquiry_items pii ON piq.item_id = pii.id
        JOIN purchase_inquiries pi ON pii.inquiry_id = pi.id
        WHERE piq.id = ? AND piq.supplier_id = ?
    """, (quote_id, user['supplier_id']))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': '报价记录不存在'})

    rec = dict(row)
    if rec['inquiry_quote_status'] == 'locked':
        conn.close()
        return jsonify({'success': False, 'message': '报价已锁定，无法修改'})

    if rec['quote_deadline']:
        try:
            deadline = datetime.strptime(rec['quote_deadline'], '%Y-%m-%d %H:%M:%S')
            if datetime.now() > deadline:
                conn.close()
                return jsonify({'success': False, 'message': '已超过报价截止时间'})
        except ValueError:
            pass

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    quantity = rec.get('quantity', 1)

    if tax_price is not None:
        tax_exempt_price = round(tax_price / (1 + tax_rate), 4) if tax_rate else tax_price
        total_amount = round(tax_price * quantity, 2)
        cursor.execute("""
            UPDATE purchase_inquiry_quotes
            SET tax_price = ?, tax_exempt_price = ?, tax_rate = ?, total_amount = ?,
                supplier_remark = ?, quote_status = 'saved', updated_at = ?
            WHERE id = ?
        """, (tax_price, tax_exempt_price, tax_rate, total_amount,
              escape(supplier_remark), now, quote_id))
    else:
        cursor.execute("""
            UPDATE purchase_inquiry_quotes
            SET supplier_remark = ?, updated_at = ?
            WHERE id = ?
        """, (escape(supplier_remark), now, quote_id))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': '报价已保存'})


# ==================== 提交报价 ====================

@supplier_bp.route('/quotes/<int:quote_id>/submit', methods=['POST'])
def submit_quote(quote_id):
    """提交报价"""
    user = _current_supplier()
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    data = request.json or {}
    tax_price = data.get('tax_price')
    tax_rate = data.get('tax_rate', 0.13)
    supplier_remark = (data.get('supplier_remark') or '').strip()

    if tax_price is None:
        return jsonify({'success': False, 'message': '请填写含税单价'})
    try:
        tax_price = float(tax_price)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '请填写有效的含税单价'})
    if tax_price <= 0:
        return jsonify({'success': False, 'message': '含税单价必须大于0'})

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT piq.id, pi.quote_status AS inquiry_quote_status,
               pi.quote_deadline, pii.quantity
        FROM purchase_inquiry_quotes piq
        JOIN purchase_inquiry_items pii ON piq.item_id = pii.id
        JOIN purchase_inquiries pi ON pii.inquiry_id = pi.id
        WHERE piq.id = ? AND piq.supplier_id = ?
    """, (quote_id, user['supplier_id']))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': '报价记录不存在'})

    rec = dict(row)
    if rec['inquiry_quote_status'] == 'locked':
        conn.close()
        return jsonify({'success': False, 'message': '报价已锁定，无法修改'})

    if rec['quote_deadline']:
        try:
            deadline = datetime.strptime(rec['quote_deadline'], '%Y-%m-%d %H:%M:%S')
            if datetime.now() > deadline:
                conn.close()
                return jsonify({'success': False, 'message': '已超过报价截止时间'})
        except ValueError:
            pass

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    quantity = rec.get('quantity', 1)
    tax_exempt_price = round(tax_price / (1 + tax_rate), 4) if tax_rate else tax_price
    total_amount = round(tax_price * quantity, 2)

    cursor.execute("""
        UPDATE purchase_inquiry_quotes
        SET tax_price = ?, tax_exempt_price = ?, tax_rate = ?, total_amount = ?,
            supplier_remark = ?, quote_status = 'submitted', submitted_at = ?, updated_at = ?
        WHERE id = ?
    """, (tax_price, tax_exempt_price, tax_rate, total_amount,
          escape(supplier_remark), now, now, quote_id))

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': '报价已提交'})
