"""
认证和权限装饰器
"""
from functools import wraps
from flask import session, jsonify


def login_required(f):
    """要求用户已登录"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user'):
            return jsonify({'success': False, 'message': '未登录'})
        return f(*args, **kwargs)
    return decorated


def require_role(*roles):
    """要求用户具有指定角色之一"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = session.get('user')
            if not user:
                return jsonify({'success': False, 'message': '未登录'})
            if user.get('role_name') not in roles:
                return jsonify({'success': False, 'message': '权限不足'})
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_admin(f):
    """要求系统管理员角色"""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = session.get('user')
        if not user:
            return jsonify({'success': False, 'message': '未登录'})
        if user.get('role_name') != '系统管理员':
            return jsonify({'success': False, 'message': '仅管理员可操作'})
        return f(*args, **kwargs)
    return decorated
