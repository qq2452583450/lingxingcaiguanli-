"""
零星材管理系统 - Flask后端
使用蓝图模块化架构
"""
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
import os
import config

app = Flask(__name__, static_folder='static')
CORS(app, supports_credentials=True)
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    raise ValueError("必须设置 SECRET_KEY 环境变量")

# ==================== 注册蓝图 ====================
from blueprints import (
    auth_bp,
    material_bp,
    inquiry_bp,
    stock_bp,
    sales_bp,
    reconciliation_bp,
    system_bp,
    dashboard_bp
)

app.register_blueprint(auth_bp)
app.register_blueprint(material_bp)
app.register_blueprint(inquiry_bp)
app.register_blueprint(stock_bp)
app.register_blueprint(sales_bp)
app.register_blueprint(reconciliation_bp)
app.register_blueprint(system_bp)
app.register_blueprint(dashboard_bp)

# ==================== 静态文件 ====================

@app.route('/')
def index():
    """主页"""
    return send_from_directory('.', 'index.html')

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
