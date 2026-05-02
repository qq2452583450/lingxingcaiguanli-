"""
数据库初始化
"""
import sqlite3
import os
import config
from datetime import datetime


def get_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """初始化数据库表"""
    conn = get_connection()
    cursor = conn.cursor()

    # 用户表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            real_name TEXT,
            role_id INTEGER,
            is_active INTEGER DEFAULT 1,
            create_time TEXT,
            FOREIGN KEY (role_id) REFERENCES roles(id)
        )
    """)

    # 角色表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_name TEXT UNIQUE NOT NULL,
            permissions TEXT
        )
    """)

    # 仓库表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warehouses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            warehouse_name TEXT NOT NULL,
            address TEXT,
            remark TEXT,
            is_default INTEGER DEFAULT 0,
            create_time TEXT
        )
    """)

    # 供应商表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
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
        CREATE TABLE IF NOT EXISTS units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_name TEXT UNIQUE NOT NULL,
            unit_code TEXT
        )
    """)

    # 材料表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materials (
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
            create_time TEXT,
            FOREIGN KEY (unit_id) REFERENCES units(id),
            FOREIGN KEY (default_supplier_id) REFERENCES suppliers(id)
        )
    """)
    # 添加税率列（如果不存在）- 使用try-except处理已存在列的情况
    try:
        cursor.execute("ALTER TABLE materials ADD COLUMN tax_rate REAL DEFAULT 0.01")
    except Exception:
        pass  # 列已存在，忽略错误
    try:
        cursor.execute("ALTER TABLE materials ADD COLUMN project_id INTEGER")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_materials_project ON materials(project_id)")
    except Exception:
        pass  # 列已存在，忽略错误

    # 添加详细规格列（如果不存在）
    try:
        cursor.execute("ALTER TABLE materials ADD COLUMN detail_spec TEXT")
    except Exception:
        pass  # 列已存在

    # 添加是否国标列（如果不存在）
    try:
        cursor.execute("ALTER TABLE materials ADD COLUMN is_national_standard INTEGER DEFAULT 0")
    except Exception:
        pass  # 列已存在

    # 添加品牌列（如果不存在）
    try:
        cursor.execute("ALTER TABLE materials ADD COLUMN brand TEXT")
    except Exception:
        pass  # 列已存在

    # 材料价格历史表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS material_price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER,
            supplier_id INTEGER,
            tax_price REAL,
            inquired_time TEXT,
            inquired_by INTEGER,
            inquiry_id INTEGER,
            FOREIGN KEY (material_id) REFERENCES materials(id),
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        )
    """)

    # 库存表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER,
            warehouse_id INTEGER,
            quantity REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            update_time TEXT,
            FOREIGN KEY (material_id) REFERENCES materials(id),
            FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
            UNIQUE(material_id, warehouse_id)
        )
    """)

    # 项目表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_code TEXT UNIQUE NOT NULL,
            project_name TEXT NOT NULL,
            contract_no TEXT,
            customer_id INTEGER,
            start_date TEXT,
            end_date TEXT,
            remark TEXT,
            create_time TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)

    # 客户表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
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

    # 询价单表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_inquiries (
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
            create_time TEXT,
            remark TEXT,
            FOREIGN KEY (applicant_id) REFERENCES users(id),
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # 询价明细表（旧表，保留用于历史数据兼容）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_inquiry_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inquiry_id INTEGER,
            material_id INTEGER,
            supplier_id INTEGER,
            this_price REAL DEFAULT 0,
            library_price REAL DEFAULT 0,
            is_lowest INTEGER DEFAULT 0,
            price_diff REAL DEFAULT 0,
            FOREIGN KEY (inquiry_id) REFERENCES purchase_inquiries(id),
            FOREIGN KEY (material_id) REFERENCES materials(id),
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        )
    """)

    # 询价材料项分组表（每种材料一行，含采购数量）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_inquiry_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inquiry_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            quantity REAL DEFAULT 1,
            library_price REAL DEFAULT 0,
            selected_quote_id INTEGER,
            tax_rate REAL DEFAULT 0.01,
            create_time TEXT,
            FOREIGN KEY (inquiry_id) REFERENCES purchase_inquiries(id) ON DELETE CASCADE,
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
    """)

    # 询价供应商报价表（每种材料的每家供应商报价一行）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_inquiry_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            supplier_id INTEGER NOT NULL,
            tax_price REAL DEFAULT 0,
            tax_exempt_price REAL DEFAULT 0,
            tax_rate REAL DEFAULT 0.13,
            total_amount REAL DEFAULT 0,
            is_lowest INTEGER DEFAULT 0,
            is_selected INTEGER DEFAULT 0,
            create_time TEXT,
            FOREIGN KEY (item_id) REFERENCES purchase_inquiry_items(id) ON DELETE CASCADE,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
        )
    """)

    # 采购单表（集采）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
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
            remark TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id),
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
            FOREIGN KEY (applicant_id) REFERENCES users(id)
        )
    """)

    # 采购明细表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_order_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            material_id INTEGER,
            quantity REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            amount REAL DEFAULT 0,
            in_quantity REAL DEFAULT 0,
            FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
    """)

    # 入库单表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_in_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            source_type TEXT DEFAULT '采购入库',
            related_order_no TEXT,
            supplier_id INTEGER,
            warehouse_id INTEGER,
            project_id INTEGER,
            operator_id INTEGER,
            in_time TEXT,
            status TEXT DEFAULT '已入库',
            create_time TEXT,
            remark TEXT,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
            FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
            FOREIGN KEY (project_id) REFERENCES projects(id),
            FOREIGN KEY (operator_id) REFERENCES users(id)
        )
    """)

    # 入库明细表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_in_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            material_id INTEGER,
            quantity REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            amount REAL DEFAULT 0,
            FOREIGN KEY (order_id) REFERENCES stock_in_orders(id),
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
    """)

    # 出库单表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_out_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            out_type TEXT DEFAULT '领用',
            customer_name TEXT,
            warehouse_id INTEGER,
            operator_id INTEGER,
            out_time TEXT,
            create_time TEXT,
            remark TEXT,
            FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
            FOREIGN KEY (operator_id) REFERENCES users(id)
        )
    """)

    # 出库明细表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_out_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            material_id INTEGER,
            quantity REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            amount REAL DEFAULT 0,
            FOREIGN KEY (order_id) REFERENCES stock_out_orders(id),
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
    """)

    # 销售单表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales_orders (
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
            remark TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id),
            FOREIGN KEY (salesperson_id) REFERENCES users(id)
        )
    """)

    # 销售明细表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales_order_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            material_id INTEGER,
            quantity REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            discount REAL DEFAULT 1.0,
            amount REAL DEFAULT 0,
            FOREIGN KEY (order_id) REFERENCES sales_orders(id),
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
    """)

    # 对账单主表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reconciliation_statements (
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
            remark TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id),
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)

    # 对账明细表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reconciliation_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            statement_id INTEGER,
            original_no TEXT,
            transaction_date TEXT,
            material_id INTEGER,
            material_name TEXT,
            specification TEXT,
            unit_id INTEGER,
            unit_name TEXT,
            quantity REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            amount REAL DEFAULT 0,
            remark TEXT,
            FOREIGN KEY (statement_id) REFERENCES reconciliation_statements(id),
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
    """)

    # 审批记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS approval_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_type TEXT,
            order_id INTEGER,
            approver_id INTEGER,
            approver_name TEXT,
            result TEXT,
            remark TEXT,
            approval_time TEXT,
            FOREIGN KEY (approver_id) REFERENCES users(id)
        )
    """)

    # 操作日志表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            module TEXT,
            action TEXT,
            target_id INTEGER,
            detail TEXT,
            create_time TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 用户-项目关联表（多对多）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            UNIQUE(user_id, project_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    return conn


def create_indexes(conn=None):
    """创建数据库索引以提升查询性能"""
    if conn is None:
        conn = get_connection()
        should_close = True
    else:
        should_close = False

    cursor = conn.cursor()

    # 材料表索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_materials_code ON materials(material_code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_materials_name ON materials(material_name)")

    # 库存表复合索引
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_material_warehouse ON inventory(material_id, warehouse_id)")

    # 询价单索引
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_inquiries_no ON purchase_inquiries(inquiry_no)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inquiries_status ON purchase_inquiries(approval_status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inquiries_applicant ON purchase_inquiries(applicant_id)")

    # 采购订单索引
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_no ON purchase_orders(order_no)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON purchase_orders(approval_status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_supplier ON purchase_orders(supplier_id)")

    # 入库单索引
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_in_no ON stock_in_orders(order_no)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_in_date ON stock_in_orders(in_time)")

    # 出库单索引
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_out_no ON stock_out_orders(order_no)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_out_date ON stock_out_orders(out_time)")

    # 销售单索引
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_no ON sales_orders(order_no)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_date ON sales_orders(create_time)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_customer ON sales_orders(customer_id)")

    # 对账单索引
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_reconciliation_no ON reconciliation_statements(statement_no)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reconciliation_period ON reconciliation_statements(period_start, period_end)")

    # 用户表索引
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)")

    # 供应商/客户索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers(supplier_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(customer_name)")

    conn.commit()

    if should_close:
        conn.close()


def insert_default_data(conn):
    """插入默认数据"""
    # 延迟导入避免循环依赖
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from helpers import hash_password

    cursor = conn.cursor()

    # 检查是否已有数据
    cursor.execute("SELECT COUNT(*) FROM roles")
    if cursor.fetchone()[0] > 0:
        return  # 已有数据，跳过

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 插入角色
    for role in config.DEFAULT_ROLES:
        cursor.execute(
            "INSERT INTO roles (role_name, permissions) VALUES (?, ?)",
            (role["name"], role["permissions"])
        )

    # 获取管理员角色ID
    cursor.execute("SELECT id FROM roles WHERE role_name = '系统管理员'")
    admin_role_id = cursor.fetchone()[0]

    # 插入管理员账号（如果未设置环境变量密码，使用临时密码）
    admin_password = config.DEFAULT_ADMIN["password"] or "admin123"  # 临时密码，登录后必须修改
    cursor.execute(
        "INSERT INTO users (username, password, real_name, role_id, is_active, create_time) VALUES (?, ?, ?, ?, ?, ?)",
        (config.DEFAULT_ADMIN["username"], hash_password(admin_password),
         config.DEFAULT_ADMIN["real_name"], admin_role_id, 1, now)
    )

    # 插入计量单位
    for unit in config.DEFAULT_UNITS:
        cursor.execute(
            "INSERT INTO units (unit_name) VALUES (?)",
            (unit,)
        )

    # 插入默认仓库
    cursor.execute(
        "INSERT INTO warehouses (warehouse_name, address, is_default, create_time) VALUES (?, ?, ?, ?)",
        ("默认仓库", "默认地址", 1, now)
    )

    conn.commit()


def check_database_exists():
    """检查数据库是否已初始化"""
    import os
    return os.path.exists(config.DATABASE_PATH)
