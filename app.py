"""
零星材管理系统 - Flask后端
使用蓝图模块化架构
"""
from flask import Flask, send_from_directory
from flask_cors import CORS
import os
import config

app = Flask(__name__, static_folder='static')
CORS(app, supports_credentials=True)
app.secret_key = os.environ.get('SECRET_KEY', 'lingxingcai_secret_key_2024')

# ==================== 注册蓝图 ====================
from blueprints import (
    auth_bp,
    material_bp,
    inquiry_bp,
    order_bp,
    stock_bp,
    sales_bp,
    reconciliation_bp,
    system_bp,
    dashboard_bp
)

app.register_blueprint(auth_bp)
app.register_blueprint(material_bp)
app.register_blueprint(inquiry_bp)
app.register_blueprint(order_bp)
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

    print("=" * 50)
    print("零星材管理系统 Web版")
    print("访问地址: http://localhost:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
