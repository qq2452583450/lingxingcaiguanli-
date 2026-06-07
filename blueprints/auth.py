"""
认证蓝图
"""
from flask import Blueprint, request, jsonify, session
from helpers import verify_password, get_db
from helpers.auth_decorators import login_required
from datetime import datetime, timedelta
import threading

auth_bp = Blueprint('auth', __name__, url_prefix='/api')

# 登录尝试追踪（线程安全）
_login_attempts = {}
_attempts_lock = threading.Lock()
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _check_rate_limit(ip):
    """检查IP是否被锁定"""
    with _attempts_lock:
        if ip in _login_attempts:
            attempts, lock_until = _login_attempts[ip]
            if attempts >= MAX_ATTEMPTS:
                if datetime.now() < lock_until:
                    remaining = (lock_until - datetime.now()).seconds // 60 + 1
                    return False, remaining
                else:
                    # 锁定已过期，重置
                    del _login_attempts[ip]
        return True, 0


def _record_failed_attempt(ip):
    """记录失败尝试"""
    with _attempts_lock:
        if ip not in _login_attempts:
            _login_attempts[ip] = (1, None)
        else:
            attempts, _ = _login_attempts[ip]
            _login_attempts[ip] = (attempts + 1, None)

            # 如果达到最大尝试次数，锁定账号
            if attempts + 1 >= MAX_ATTEMPTS:
                lock_until = datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)
                _login_attempts[ip] = (MAX_ATTEMPTS, lock_until)


def _reset_attempts(ip):
    """重置登录尝试（成功登录后）"""
    with _attempts_lock:
        if ip in _login_attempts:
            del _login_attempts[ip]


@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    # 获取客户端IP
    ip = request.remote_addr or 'unknown'

    # 检查是否被锁定
    allowed, remaining = _check_rate_limit(ip)
    if not allowed:
        return jsonify({'success': False, 'message': f'登录失败次数过多，请 {remaining} 分钟后再试'})

    data = request.json
    username = data.get('username', '')
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'success': False, 'message': '请输入用户名和密码'})

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.id, u.username, u.password, u.real_name, u.role_id, u.is_active,
               r.role_name, r.permissions
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.id
        WHERE u.username = ?
    """, (username,))
    row = cursor.fetchone()

    if not row:
        _record_failed_attempt(ip)
        return jsonify({'success': False, 'message': '用户名或密码错误'})

    if not row['is_active']:
        return jsonify({'success': False, 'message': '账号已被禁用'})

    if not verify_password(password, row['password']):
        _record_failed_attempt(ip)
        allowed, remaining = _check_rate_limit(ip)
        if not allowed:
            return jsonify({'success': False, 'message': f'登录失败次数过多，请 {remaining} 分钟后再试'})
        return jsonify({'success': False, 'message': '用户名或密码错误'})

    # 登录成功，重置尝试次数
    _reset_attempts(ip)

    user = {
        'id': row['id'],
        'username': row['username'],
        'real_name': row['real_name'],
        'role_name': row['role_name'],
        'permissions': row['permissions'] or ''
    }
    session['user'] = user

    return jsonify({'success': True, 'user': user})


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """退出登录"""
    session.clear()
    return jsonify({'success': True})


@auth_bp.route('/current_user', methods=['GET'])
def current_user():
    """获取当前用户"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})
    return jsonify({'success': True, 'user': user})
