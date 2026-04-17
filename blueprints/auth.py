"""
认证蓝图
"""
from flask import Blueprint, request, jsonify, session
from helpers import verify_password

auth_bp = Blueprint('auth', __name__, url_prefix='/api')


def get_db():
    """获取数据库连接"""
    from flask import current_app, g
    if 'db' not in g:
        import sqlite3
        import config
        g.db = sqlite3.connect(config.DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
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
        return jsonify({'success': False, 'message': '用户名或密码错误'})

    if not row['is_active']:
        return jsonify({'success': False, 'message': '账号已被禁用'})

    if not verify_password(password, row['password']):
        return jsonify({'success': False, 'message': '用户名或密码错误'})

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
