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
            must_change_password INTEGER DEFAULT 0,
            FOREIGN KEY (role_id) REFERENCES roles(id)
        )
    """)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0")
    except Exception:
        pass

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
    cursor.execute("""
        UPDATE warehouses
        SET warehouse_name = '材料基地'
        WHERE is_default = 1 AND warehouse_name = '默认仓库'
    """)

    # 供应商表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_name TEXT NOT NULL,
            contact TEXT,
            phone TEXT,
            address TEXT,
            user_id INTEGER,
            tax_rate REAL,
            remark TEXT,
            create_time TEXT
        )
    """)
    try:
        cursor.execute("ALTER TABLE suppliers ADD COLUMN user_id INTEGER")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE suppliers ADD COLUMN tax_rate REAL")
    except Exception:
        pass

    # 供应商经营范围字段
    try:
        cursor.execute("ALTER TABLE suppliers ADD COLUMN business_scope TEXT")
    except Exception:
        pass

    # 供应商资料是否完善的标记
    try:
        cursor.execute("ALTER TABLE supplier_accounts ADD COLUMN profile_completed INTEGER DEFAULT 0")
    except Exception:
        pass

    # 供应商账号表（供应商独立登录，不与内部 users 混用）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS supplier_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            is_active INTEGER DEFAULT 0,
            create_time TEXT,
            last_login_time TEXT,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
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

    # 添加现金含税价相关列（如果不存在）
    try:
        cursor.execute("ALTER TABLE materials ADD COLUMN is_cash_price INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE materials ADD COLUMN cash_price REAL DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE materials ADD COLUMN cash_tax_price REAL DEFAULT 0")
    except Exception:
        pass

    # 添加重量列（如果不存在）
    try:
        cursor.execute("ALTER TABLE materials ADD COLUMN weight REAL DEFAULT 0")
    except Exception:
        pass

    # 添加是否国标和是否现金含税价到询价材料项（如果不存在）
    try:
        cursor.execute("ALTER TABLE purchase_inquiry_items ADD COLUMN is_national_standard INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE purchase_inquiry_items ADD COLUMN is_cash_price INTEGER DEFAULT 0")
    except Exception:
        pass
    # 添加详细规格和品牌到询价材料项（如果不存在）
    try:
        cursor.execute("ALTER TABLE purchase_inquiry_items ADD COLUMN detail_spec TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE purchase_inquiry_items ADD COLUMN brand TEXT")
    except Exception:
        pass

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

    # 材料基地库存独立于项目库存，只有明确入库基地后才会产生记录。
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS base_inventory (
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
            UNIQUE(material_id, region),
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
    """)
    # 兼容已创建的旧版基地库存表：允许基地自有材料不依赖项目材料库。
    cursor.execute("PRAGMA table_info(base_inventory)")
    base_inventory_columns = {row['name']: row for row in cursor.fetchall()}
    text_columns = {
        'material_name': 'TEXT',
        'specification': 'TEXT',
        'detail_spec': 'TEXT',
        'unit_name': 'TEXT',
        'region': "TEXT DEFAULT '成都'",
        'remark': 'TEXT',
    }
    for column_name, column_type in text_columns.items():
        if column_name not in base_inventory_columns:
            cursor.execute(f"ALTER TABLE base_inventory ADD COLUMN {column_name} {column_type}")
    cursor.execute("UPDATE base_inventory SET region = '成都' WHERE region IS NULL OR region = ''")

    cursor.execute("PRAGMA table_info(base_inventory)")
    base_inventory_columns = {row['name']: row for row in cursor.fetchall()}
    cursor.execute("PRAGMA index_list(base_inventory)")
    unique_material_only_index = False
    for index_row in cursor.fetchall():
        if not index_row['unique']:
            continue
        cursor.execute(f"PRAGMA index_info({index_row['name']})")
        index_columns = [info['name'] for info in cursor.fetchall()]
        if index_columns == ['material_id']:
            unique_material_only_index = True
            break
    if base_inventory_columns.get('material_id') and (
        base_inventory_columns['material_id']['notnull'] or unique_material_only_index
    ):
        cursor.execute("""
            CREATE TABLE base_inventory_new (
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
                UNIQUE(material_id, region),
                FOREIGN KEY (material_id) REFERENCES materials(id)
            )
        """)
        cursor.execute("""
            INSERT INTO base_inventory_new (
                id, material_id, material_name, specification, detail_spec, unit_name,
                region, quantity, unit_price, update_time, remark
            )
            SELECT id, material_id, material_name, specification, detail_spec, unit_name,
                   COALESCE(NULLIF(region, ''), '成都'), quantity, unit_price, update_time, remark
            FROM base_inventory
        """)
        cursor.execute("DROP TABLE base_inventory")
        cursor.execute("ALTER TABLE base_inventory_new RENAME TO base_inventory")

    # 基地到项目调拨台账，保留材料快照、折旧价格和运费。
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS base_inventory_transfers (
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
            remark TEXT,
            FOREIGN KEY (base_inventory_id) REFERENCES base_inventory(id),
            FOREIGN KEY (project_id) REFERENCES projects(id),
            FOREIGN KEY (operator_id) REFERENCES users(id)
        )
    """)
    cursor.execute("PRAGMA table_info(base_inventory_transfers)")
    base_transfer_columns = {row['name'] for row in cursor.fetchall()}
    if 'batch_no' not in base_transfer_columns:
        cursor.execute("ALTER TABLE base_inventory_transfers ADD COLUMN batch_no TEXT")

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
            supplier_id INTEGER,
            FOREIGN KEY (order_id) REFERENCES stock_in_orders(id),
            FOREIGN KEY (material_id) REFERENCES materials(id),
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
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
            team_name TEXT,
            receiver_name TEXT,
            project_id INTEGER,
            FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
            FOREIGN KEY (operator_id) REFERENCES users(id),
            FOREIGN KEY (project_id) REFERENCES projects(id)
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
            team_name TEXT,
            receiver_name TEXT,
            FOREIGN KEY (order_id) REFERENCES stock_out_orders(id),
            FOREIGN KEY (material_id) REFERENCES materials(id)
        )
    """)

    # 调拨单表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_transfer_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transfer_no TEXT UNIQUE NOT NULL,
            from_warehouse_id INTEGER NOT NULL,
            to_warehouse_id INTEGER NOT NULL,
            operator_id INTEGER,
            transfer_time TEXT,
            create_time TEXT,
            remark TEXT,
            FOREIGN KEY (from_warehouse_id) REFERENCES warehouses(id),
            FOREIGN KEY (to_warehouse_id) REFERENCES warehouses(id),
            FOREIGN KEY (operator_id) REFERENCES users(id)
        )
    """)

    # 调拨明细表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_transfer_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            quantity REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            amount REAL DEFAULT 0,
            FOREIGN KEY (order_id) REFERENCES stock_transfer_orders(id),
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

    # 甲供材料专项量控台账
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS owner_material_controls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            data_status TEXT DEFAULT '正式',
            control_level TEXT DEFAULT 'A类重点',
            building TEXT,
            work_item TEXT,
            material_name TEXT NOT NULL,
            specification TEXT,
            unit TEXT NOT NULL,
            contract_quantity REAL DEFAULT 0,
            budget_quantity REAL DEFAULT 0,
            change_quantity REAL DEFAULT 0,
            arrival_quantity REAL DEFAULT 0,
            issued_quantity REAL DEFAULT 0,
            theoretical_quantity REAL DEFAULT 0,
            site_surplus REAL DEFAULT 0,
            contractor_inventory REAL DEFAULT 0,
            transit_quantity REAL DEFAULT 0,
            reason_measures TEXT,
            responsible_person TEXT,
            updated_at TEXT,
            remark TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # 甲供材料月度需求计划
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS owner_monthly_demands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            plan_month TEXT NOT NULL,
            building TEXT,
            construction_area TEXT,
            material_name TEXT NOT NULL,
            specification TEXT,
            unit TEXT NOT NULL,
            planned_quantity REAL DEFAULT 0,
            current_inventory REAL DEFAULT 0,
            contractor_inventory REAL DEFAULT 0,
            transit_quantity REAL DEFAULT 0,
            required_date TEXT,
            review_comment TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # 甲供材料到货、领用、退库和调拨原始记录
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS owner_material_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            business_date TEXT NOT NULL,
            business_type TEXT NOT NULL,
            building TEXT,
            construction_area TEXT,
            material_name TEXT NOT NULL,
            specification TEXT,
            unit TEXT NOT NULL,
            quantity REAL DEFAULT 0,
            supplier_source TEXT,
            document_no TEXT,
            acceptance_result TEXT,
            quality_documents TEXT,
            receiving_unit TEXT,
            signer TEXT,
            registrant TEXT,
            remark TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # 甲供材料预警问题闭环
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS owner_warning_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            warning_date TEXT NOT NULL,
            warning_status TEXT NOT NULL,
            building TEXT,
            material_name TEXT NOT NULL,
            specification TEXT,
            variance_quantity REAL DEFAULT 0,
            loss_rate REAL DEFAULT 0,
            problem_description TEXT NOT NULL,
            reason_category TEXT,
            corrective_action TEXT,
            responsible_person TEXT,
            due_date TEXT,
            closure_status TEXT DEFAULT '待处理',
            review_result TEXT,
            reviewer TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # 项目级甲供材预警参数
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS owner_supplied_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER UNIQUE NOT NULL,
            yellow_loss_rate REAL DEFAULT 0.02,
            red_loss_rate REAL DEFAULT 0.03,
            yellow_remaining_threshold REAL DEFAULT 0,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # 供应商报价相关扩展字段
    for col, ddl in [
        ('quote_status', "ALTER TABLE purchase_inquiries ADD COLUMN quote_status TEXT DEFAULT 'draft'"),
        ('quote_deadline', "ALTER TABLE purchase_inquiries ADD COLUMN quote_deadline TEXT"),
    ]:
        try:
            cursor.execute(ddl)
        except Exception:
            pass

    for col, ddl in [
        ('quote_status', "ALTER TABLE purchase_inquiry_quotes ADD COLUMN quote_status TEXT DEFAULT 'pending'"),
        ('submitted_at', "ALTER TABLE purchase_inquiry_quotes ADD COLUMN submitted_at TEXT"),
        ('updated_at', "ALTER TABLE purchase_inquiry_quotes ADD COLUMN updated_at TEXT"),
        ('supplier_remark', "ALTER TABLE purchase_inquiry_quotes ADD COLUMN supplier_remark TEXT"),
    ]:
        try:
            cursor.execute(ddl)
        except Exception:
            pass

    # supplier_accounts 索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_supplier_accounts_supplier ON supplier_accounts(supplier_id)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_supplier_accounts_username ON supplier_accounts(username)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS petty_cash_loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_no TEXT UNIQUE NOT NULL,
            project_id INTEGER NOT NULL,
            loan_date TEXT NOT NULL,
            total_amount REAL DEFAULT 0,
            payment_file_path TEXT,
            payment_file_name TEXT,
            creator_id INTEGER,
            remark TEXT,
            create_time TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id),
            FOREIGN KEY (creator_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS petty_cash_usages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usage_no TEXT UNIQUE NOT NULL,
            loan_id INTEGER NOT NULL,
            use_date TEXT NOT NULL,
            expense_type TEXT NOT NULL,
            amount REAL DEFAULT 0,
            handler TEXT,
            description TEXT,
            proof_file_path TEXT,
            proof_file_name TEXT,
            creator_id INTEGER,
            create_time TEXT,
            FOREIGN KEY (loan_id) REFERENCES petty_cash_loans(id),
            FOREIGN KEY (creator_id) REFERENCES users(id)
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
    cursor.execute("DROP INDEX IF EXISTS idx_base_inventory_material")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_base_inventory_material_region ON base_inventory(material_id, region)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_base_inventory_transfers_project ON base_inventory_transfers(project_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_base_inventory_transfers_time ON base_inventory_transfers(transfer_time)")

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

    # 调拨单索引
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_transfer_no ON stock_transfer_orders(transfer_no)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_transfer_date ON stock_transfer_orders(transfer_time)")

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

    # 甲供材料专项量控
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_owner_controls_project ON owner_material_controls(project_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_owner_demands_project_month ON owner_monthly_demands(project_id, plan_month)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_owner_transactions_project_date ON owner_material_transactions(project_id, business_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_owner_issues_project_status ON owner_warning_issues(project_id, closure_status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_petty_cash_loans_project ON petty_cash_loans(project_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_petty_cash_usages_loan ON petty_cash_usages(loan_id)")

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
        ("材料基地", "默认地址", 1, now)
    )

    conn.commit()


def check_database_exists():
    """检查数据库是否已初始化"""
    import os
    return os.path.exists(config.DATABASE_PATH)
