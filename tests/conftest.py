"""
Pytest配置和fixtures
"""
import pytest
import os
import sys
import tempfile
import sqlite3
import gc

# 添加项目根目录到path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def test_db():
    """创建临时测试数据库"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    # 注入到 config 使 helpers.get_db() 使用测试库
    import config
    _orig_path = config.DATABASE_PATH
    config.DATABASE_PATH = path

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
            create_time TEXT,
            must_change_password INTEGER DEFAULT 0
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
            detail_spec TEXT,
            is_national_standard INTEGER DEFAULT 0,
            brand TEXT,
            unit_id INTEGER,
            tax_price REAL DEFAULT 0,
            tax_exempt_price REAL DEFAULT 0,
            is_cash_price INTEGER DEFAULT 0,
            cash_price REAL DEFAULT 0,
            cash_tax_price REAL DEFAULT 0,
            freight REAL DEFAULT 0,
            remark TEXT,
            default_supplier_id INTEGER,
            inventory_min REAL DEFAULT 0,
            inventory_max REAL DEFAULT 0,
            create_time TEXT,
            tax_rate REAL DEFAULT 0.01,
            project_id INTEGER,
            weight REAL DEFAULT 0
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
            business_scope TEXT,
            user_id INTEGER,
            tax_rate REAL,
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

    cursor.execute("""
        CREATE TABLE base_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER,
            material_name TEXT,
            specification TEXT,
            detail_spec TEXT,
            unit_name TEXT,
            region TEXT DEFAULT '成都',
            quantity REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            update_time TEXT,
            remark TEXT,
            UNIQUE(material_id, region)
        )
    """)

    cursor.execute("""
        CREATE TABLE base_inventory_transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transfer_no TEXT UNIQUE NOT NULL,
            base_inventory_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            material_name TEXT NOT NULL,
            specification TEXT,
            detail_spec TEXT,
            unit_name TEXT,
            quantity REAL DEFAULT 0,
            original_unit_price REAL DEFAULT 0,
            depreciated_unit_price REAL DEFAULT 0,
            freight REAL DEFAULT 0,
            total_amount REAL DEFAULT 0,
            operator_id INTEGER,
            transfer_time TEXT,
            batch_no TEXT,
            remark TEXT
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
            project_id INTEGER,
            total_amount REAL DEFAULT 0,
            is_below_library_price INTEGER DEFAULT 0,
            approval_status TEXT DEFAULT '待审批',
            approval_remark TEXT,
            approver_id INTEGER,
            approve_time TEXT,
            library_price_updated INTEGER DEFAULT 0,
            quote_status TEXT DEFAULT 'draft',
            quote_deadline TEXT,
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
            amount REAL DEFAULT 0,
            supplier_id INTEGER,
            warehouse_id INTEGER DEFAULT 1
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
            remark TEXT,
            team_name TEXT,
            receiver_name TEXT,
            project_id INTEGER
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
            amount REAL DEFAULT 0,
            team_name TEXT,
            receiver_name TEXT
        )
    """)

    # 调拨单表
    cursor.execute("""
        CREATE TABLE stock_transfer_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transfer_no TEXT UNIQUE NOT NULL,
            from_warehouse_id INTEGER NOT NULL,
            to_warehouse_id INTEGER NOT NULL,
            operator_id INTEGER,
            transfer_time TEXT,
            create_time TEXT,
            remark TEXT
        )
    """)

    # 调拨明细表
    cursor.execute("""
        CREATE TABLE stock_transfer_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
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

    # 供应商账号表
    cursor.execute("""
        CREATE TABLE supplier_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            is_active INTEGER DEFAULT 0,
            profile_completed INTEGER DEFAULT 0,
            create_time TEXT,
            last_login_time TEXT,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        )
    """)

    # 采购询价材料项表
    cursor.execute("""
        CREATE TABLE petty_cash_loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_no TEXT UNIQUE NOT NULL,
            project_id INTEGER NOT NULL,
            loan_date TEXT NOT NULL,
            total_amount REAL DEFAULT 0,
            payment_file_path TEXT,
            payment_file_name TEXT,
            creator_id INTEGER,
            remark TEXT,
            create_time TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE petty_cash_usages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usage_no TEXT UNIQUE NOT NULL,
            loan_id INTEGER NOT NULL,
            use_date TEXT NOT NULL,
            expense_type TEXT NOT NULL,
            amount REAL DEFAULT 0,
            handler TEXT,
            supplier_name TEXT,
            material_name TEXT,
            invoice_amount REAL DEFAULT 0,
            invoice_type TEXT,
            description TEXT,
            proof_file_path TEXT,
            proof_file_name TEXT,
            creator_id INTEGER,
            create_time TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE purchase_inquiry_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inquiry_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            quantity REAL DEFAULT 1,
            library_price REAL DEFAULT 0,
            selected_quote_id INTEGER,
            tax_rate REAL DEFAULT 0.01,
            is_national_standard INTEGER DEFAULT 0,
            is_cash_price INTEGER DEFAULT 0,
            detail_spec TEXT,
            brand TEXT,
            create_time TEXT,
            FOREIGN KEY (inquiry_id) REFERENCES purchase_inquiries(id) ON DELETE CASCADE,
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
    """)

    # 采购询价报价表
    cursor.execute("""
        CREATE TABLE purchase_inquiry_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            supplier_id INTEGER NOT NULL,
            tax_price REAL DEFAULT 0,
            tax_exempt_price REAL DEFAULT 0,
            tax_rate REAL DEFAULT 0.13,
            total_amount REAL DEFAULT 0,
            is_lowest INTEGER DEFAULT 0,
            is_selected INTEGER DEFAULT 0,
            quote_status TEXT DEFAULT 'pending',
            submitted_at TEXT,
            updated_at TEXT,
            supplier_remark TEXT,
            create_time TEXT,
            FOREIGN KEY (item_id) REFERENCES purchase_inquiry_items(id) ON DELETE CASCADE,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        )
    """)

    # 用户项目关联表
    cursor.execute("""
        CREATE TABLE user_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            UNIQUE(user_id, project_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE petty_cash_usage_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usage_id INTEGER NOT NULL,
            file_path TEXT,
            file_name TEXT NOT NULL,
            create_time TEXT
        )
    """)

    from database.exam_schema import init_exam_schema
    init_exam_schema(conn)
    conn.commit()
    conn.close()

    # 返回一个可当作连接使用的辅助对象
    # 每次 cursor() 开新连接，close() 后下次 cursor() 自动重开
    class _TestDB:
        def __init__(self, db_path):
            self._path = db_path
            self._conn = None

        def __fspath__(self):
            return self._path

        def _ensure_conn(self):
            if self._conn is None:
                self._conn = sqlite3.connect(self._path, timeout=10)
                self._conn.row_factory = sqlite3.Row
            return self._conn

        def cursor(self):
            return self._ensure_conn().cursor()

        def execute(self, sql, params=()):
            cur = self._ensure_conn().cursor()
            cur.execute(sql, params)
            self._conn.commit()
            return cur

        def commit(self):
            if self._conn:
                self._conn.commit()

        def close(self):
            if self._conn:
                self._conn.close()
                self._conn = None

    db = _TestDB(path)
    yield db

    db.close()
    gc.collect()
    os.unlink(path)
    config.DATABASE_PATH = _orig_path  # 恢复


@pytest.fixture
def app(test_db):
    """创建测试用Flask应用，注册真实蓝图"""
    from flask import Flask
    from helpers.db_helper import close_db

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.secret_key = 'test_secret_key'
    app.teardown_appcontext(close_db)

    # 注册真实蓝图（config.DATABASE_PATH 已由 test_db fixture 设为临时文件路径）
    from blueprints import (
        auth_bp, material_bp, inquiry_bp, stock_bp,
        sales_bp, reconciliation_bp, system_bp, dashboard_bp, transfer_bp,
        supplier_bp, petty_cash_bp, exam_bp
    )
    app.register_blueprint(auth_bp)
    app.register_blueprint(material_bp)
    app.register_blueprint(inquiry_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(reconciliation_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(transfer_bp)
    app.register_blueprint(supplier_bp)
    app.register_blueprint(petty_cash_bp)
    app.register_blueprint(exam_bp)

    return app


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return app.test_client()
