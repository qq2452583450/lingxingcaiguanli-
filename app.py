"""
零星材管理系统 - Flask后端
使用蓝图模块化架构
"""
from flask import Flask, send_from_directory, jsonify, request, session
from flask_cors import CORS
import os
import secrets
import config

app = Flask(__name__, static_folder='static')
CORS(app, supports_credentials=True)
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    raise ValueError("必须设置 SECRET_KEY 环境变量")

# 注册数据库连接清理
from helpers.db_helper import close_db
app.teardown_appcontext(close_db)

# ==================== CSRF 保护 ====================

@app.before_request
def csrf_protect():
    """对写操作验证 CSRF token"""
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    # 跳过登录（登录时还没有 session token）
    if request.path in ('/api/login', '/api/supplier/login', '/api/supplier/register'):
        return
    token = request.headers.get('X-CSRF-Token', '')
    if not token or token != session.get('csrf_token', ''):
        return jsonify({'success': False, 'message': 'CSRF 验证失败，请刷新页面重试'}), 403


@app.route('/api/csrf-token', methods=['GET'])
def get_csrf_token():
    """获取 CSRF token"""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return jsonify({'success': True, 'csrf_token': session['csrf_token']})

# ==================== 集中式错误处理 ====================

import logging
import traceback
import sys

# 修复 Windows GBK 控制台编码问题
if sys.platform == 'win32':
    for stream_name in ('stdout', 'stderr'):
        stream = getattr(sys, stream_name)
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.ERROR, format='%(asctime)s [%(levelname)s] %(message)s')


@app.errorhandler(Exception)
def handle_exception(e):
    """全局异常处理：记录堆栈，返回 JSON 错误响应"""
    logging.error(f"Unhandled error: {e}\n{traceback.format_exc()}")
    return jsonify({'success': False, 'message': '服务器内部错误'}), 500


@app.errorhandler(404)
def handle_not_found(e):
    return jsonify({'success': False, 'message': '接口不存在'}), 404


@app.errorhandler(403)
def handle_forbidden(e):
    return jsonify({'success': False, 'message': '权限不足'}), 403

# ==================== 注册蓝图 ====================
from blueprints import (
    auth_bp,
    material_bp,
    inquiry_bp,
    stock_bp,
    sales_bp,
    reconciliation_bp,
    system_bp,
    dashboard_bp,
    owner_supplied_bp,
    transfer_bp,
    supplier_bp
)

app.register_blueprint(auth_bp)
app.register_blueprint(material_bp)
app.register_blueprint(inquiry_bp)
app.register_blueprint(stock_bp)
app.register_blueprint(sales_bp)
app.register_blueprint(reconciliation_bp)
app.register_blueprint(system_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(owner_supplied_bp)
app.register_blueprint(transfer_bp)
app.register_blueprint(supplier_bp)

# ==================== 静态文件 ====================

@app.route('/')
def index():
    """主页"""
    return send_from_directory('.', 'index.html')

@app.route('/supplier-portal')
def supplier_portal():
    """供应商报价门户"""
    return send_from_directory('.', 'supplier-portal.html')

@app.route('/<path:path>')
def static_files(path):
    """静态文件"""
    if path.startswith('api/'):
        return jsonify({'success': False, 'message': 'API not found'}), 404
    return send_from_directory('.', path)

# ==================== 启动 ====================

if __name__ == '__main__':
    # 初始化数据库
    from database.init_db import init_database, insert_default_data, check_database_exists, create_indexes
    init_database()

    # 创建索引（幂等操作，已存在会忽略）
    from database.init_db import get_connection as db_conn
    conn = db_conn()
    create_indexes(conn)
    conn.close()

    if not check_database_exists():
        conn = db_conn()
        insert_default_data(conn)
        conn.close()
    
    # 自动修复数据库表结构（确保与代码定义一致）
    from database.auto_fix import auto_fix_database
    auto_fix_database()

    print("=" * 50)
    print("零星材管理系统 Web版")
    print("访问地址: http://localhost:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true')
