"""
Pytest配置和fixtures
"""
import pytest
import os
import sys
import tempfile
import sqlite3

# 添加项目根目录到path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def test_db():
    """创建临时测试数据库"""
    # 使用临时文件
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    # 连接并初始化
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    # 创建表结构
    cursor = conn.cursor()

    # 用户表
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            real_name TEXT,
            role_id INTEGER,
            is_active INTEGER DEFAULT 1,
            create_time TEXT
        )
    """)

    # 角色表
    cursor.execute("""
        CREATE TABLE roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_name TEXT UNIQUE NOT NULL,
            permissions TEXT
        )
    """)

    # 材料表
    cursor.execute("""
        CREATE TABLE materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_code TEXT UNIQUE NOT NULL,
            material_name TEXT NOT NULL,
            specification TEXT,
            unit_id INTEGER,
            tax_price REAL DEFAULT 0,
            tax_exempt_price REAL DEFAULT 0,
            freight REAL DEFAULT 0,
            remark TEXT,
            default_supplier_id INTEGER,
            inventory_min REAL DEFAULT 0,
            inventory_max REAL DEFAULT 0,
            create_time TEXT
        )
    """)

    # 供应商表
    cursor.execute("""
        CREATE TABLE suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_name TEXT NOT NULL,
            contact TEXT,
            phone TEXT,
            address TEXT,
            remark TEXT,
            create_time TEXT
        )
    """)

    # 计量单位表
    cursor.execute("""
        CREATE TABLE units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_name TEXT UNIQUE NOT NULL,
            unit_code TEXT
        )
    """)

    # 仓库表
    cursor.execute("""
        CREATE TABLE warehouses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            warehouse_name TEXT NOT NULL,
            address TEXT,
            remark TEXT,
            is_default INTEGER DEFAULT 0,
            create_time TEXT
        )
    """)

    # 库存表
    cursor.execute("""
        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER,
            warehouse_id INTEGER,
            quantity REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            update_time TEXT,
            UNIQUE(material_id, warehouse_id)
        )
    """)

    # 客户表
    cursor.execute("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_code TEXT UNIQUE NOT NULL,
            customer_name TEXT NOT NULL,
            address TEXT,
            phone TEXT,
            contact TEXT,
            initial_balance REAL DEFAULT 0,
            remark TEXT,
            create_time TEXT
        )
    """)

    # 项目表
    cursor.execute("""
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_code TEXT UNIQUE NOT NULL,
            project_name TEXT NOT NULL,
            contract_no TEXT,
            customer_id INTEGER,
            start_date TEXT,
            end_date TEXT,
            remark TEXT,
            create_time TEXT
        )
    """)

    # 询价单表
    cursor.execute("""
        CREATE TABLE purchase_inquiries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inquiry_no TEXT UNIQUE NOT NULL,
            inquiry_date TEXT,
            applicant_id INTEGER,
            total_amount REAL DEFAULT 0,
            is_below_library_price INTEGER DEFAULT 0,
            approval_status TEXT DEFAULT '待审批',
            approval_remark TEXT,
            approver_id INTEGER,
            approve_time TEXT,
            library_price_updated INTEGER DEFAULT 0,
            create_time TEXT,
            remark TEXT
        )
    """)

    # 询价明细表
    cursor.execute("""
        CREATE TABLE purchase_inquiry_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inquiry_id INTEGER,
            material_id INTEGER,
            supplier_id INTEGER,
            this_price REAL DEFAULT 0,
            library_price REAL DEFAULT 0,
            is_lowest INTEGER DEFAULT 0,
            price_diff REAL DEFAULT 0,
            quantity REAL DEFAULT 1
        )
    """)

    # 采购单表
    cursor.execute("""
        CREATE TABLE purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            order_type TEXT DEFAULT '集采',
            project_id INTEGER,
            supplier_id INTEGER,
            total_amount REAL DEFAULT 0,
            applicant_id INTEGER,
            approval_status TEXT DEFAULT '待审批',
            approval_remark TEXT,
            approver_id INTEGER,
            approve_time TEXT,
            purchase_status TEXT DEFAULT '待入库',
            create_time TEXT,
            remark TEXT
        )
    """)

    # 采购明细表
    cursor.execute("""
        CREATE TABLE purchase_order_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            material_id INTEGER,
            quantity REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            amount REAL DEFAULT 0,
            in_quantity REAL DEFAULT 0
        )
    """)

    # 入库单表
    cursor.execute("""
        CREATE TABLE stock_in_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            source_type TEXT DEFAULT '采购入库',
            related_order_no TEXT,
            supplier_id INTEGER,
            warehouse_id INTEGER,
            operator_id INTEGER,
            in_time TEXT,
            status TEXT DEFAULT '已入库',
            create_time TEXT,
            remark TEXT
        )
    """)

    # 入库明细表
    cursor.execute("""
        CREATE TABLE stock_in_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            material_id INTEGER,
            quantity REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            amount REAL DEFAULT 0
        )
    """)

    # 出库单表
    cursor.execute("""
        CREATE TABLE stock_out_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            out_type TEXT DEFAULT '领用',
            customer_name TEXT,
            warehouse_id INTEGER,
            operator_id INTEGER,
            out_time TEXT,
            create_time TEXT,
            remark TEXT
        )
    """)

    # 出库明细表
    cursor.execute("""
        CREATE TABLE stock_out_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            material_id INTEGER,
            quantity REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            amount REAL DEFAULT 0
        )
    """)

    # 销售单表
    cursor.execute("""
        CREATE TABLE sales_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            order_type TEXT DEFAULT '零售',
            customer_id INTEGER,
            customer_name TEXT,
            total_amount REAL DEFAULT 0,
            received_amount REAL DEFAULT 0,
            payment_status TEXT DEFAULT '未付款',
            print_count INTEGER DEFAULT 0,
            salesperson_id INTEGER,
            create_time TEXT,
            remark TEXT
        )
    """)

    # 销售明细表
    cursor.execute("""
        CREATE TABLE sales_order_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            material_id INTEGER,
            quantity REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            discount REAL DEFAULT 1.0,
            amount REAL DEFAULT 0
        )
    """)

    # 对账单主表
    cursor.execute("""
        CREATE TABLE reconciliation_statements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            statement_no TEXT UNIQUE NOT NULL,
            project_id INTEGER,
            supplier_id INTEGER,
            customer_id INTEGER,
            contract_no TEXT,
            period_start TEXT,
            period_end TEXT,
            total_amount REAL DEFAULT 0,
            tax_rate REAL DEFAULT 0.01,
            tax_exempt_amount REAL DEFAULT 0,
            total_paid REAL DEFAULT 0,
            total_invoiced REAL DEFAULT 0,
            total_received REAL DEFAULT 0,
            balance_due REAL DEFAULT 0,
            status TEXT DEFAULT '草稿',
            print_count INTEGER DEFAULT 0,
            create_time TEXT,
            remark TEXT
        )
    """)

    # 对账明细表
    cursor.execute("""
        CREATE TABLE reconciliation_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            statement_id INTEGER,
            original_no TEXT,
            transaction_date TEXT,
            material_id INTEGER,
            specification TEXT,
            unit_id INTEGER,
            quantity REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            amount REAL DEFAULT 0,
            remark TEXT
        )
    """)

    # 审批记录表
    cursor.execute("""
        CREATE TABLE approval_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_type TEXT,
            order_id INTEGER,
            approver_id INTEGER,
            approver_name TEXT,
            result TEXT,
            remark TEXT,
            approval_time TEXT
        )
    """)

    conn.commit()

    yield conn

    # 清理
    conn.close()
    os.unlink(path)


@pytest.fixture
def app(test_db):
    """创建测试用Flask应用"""
    from flask import Flask
    from flask_cors import CORS

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.secret_key = 'test_secret_key'
    CORS(app, supports_credentials=True)

    # 注入测试数据库连接
    def get_test_db():
        test_db.row_factory = sqlite3.Row
        return test_db

    # 导入路由（这里需要重构后的结构）
    # 暂时使用内联路由进行测试
    @app.route('/api/login', methods=['POST'])
    def login():
        from flask import request, jsonify, session
        from helpers import verify_password

        data = request.json
        username = data.get('username', '')
        password = data.get('password', '')

        if not username or not password:
            return jsonify({'success': False, 'message': '请输入用户名和密码'})

        cursor = test_db.cursor()
        cursor.execute("""
            SELECT u.id, u.username, u.real_name, u.role_id, u.is_active,
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

    @app.route('/api/current_user', methods=['GET'])
    def current_user():
        from flask import session, jsonify
        user = session.get('user')
        if not user:
            return jsonify({'success': False, 'message': '未登录'})
        return jsonify({'success': True, 'user': user})

    return app


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return app.test_client()
