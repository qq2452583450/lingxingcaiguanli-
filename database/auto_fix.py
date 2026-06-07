"""
数据库自动修复模块
确保数据库表结构与代码定义一致，覆盖所有表
"""
import sqlite3
import config

def auto_fix_database():
    """自动检测并修复数据库表结构"""
    print("检查数据库表结构...")

    conn = sqlite3.connect(config.DATABASE_PATH)
    cursor = conn.cursor()

    table_schemas = {
        'users': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'username': 'TEXT UNIQUE NOT NULL',
            'password': 'TEXT NOT NULL',
            'real_name': 'TEXT',
            'role_id': 'INTEGER',
            'is_active': 'INTEGER DEFAULT 1',
            'create_time': 'TEXT',
        },
        'roles': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'role_name': 'TEXT UNIQUE NOT NULL',
            'permissions': 'TEXT',
        },
        'user_projects': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'user_id': 'INTEGER NOT NULL',
            'project_id': 'INTEGER NOT NULL',
        },
        'warehouses': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'warehouse_name': 'TEXT NOT NULL',
            'address': 'TEXT',
            'remark': 'TEXT',
            'is_default': 'INTEGER DEFAULT 0',
            'create_time': 'TEXT',
        },
        'suppliers': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'supplier_name': 'TEXT NOT NULL',
            'contact': 'TEXT',
            'phone': 'TEXT',
            'address': 'TEXT',
            'remark': 'TEXT',
            'tax_rate': 'REAL',
            'create_time': 'TEXT',
        },
        'units': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'unit_name': 'TEXT UNIQUE NOT NULL',
            'unit_code': 'TEXT',
        },
        'customers': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'customer_code': 'TEXT UNIQUE NOT NULL',
            'customer_name': 'TEXT NOT NULL',
            'address': 'TEXT',
            'phone': 'TEXT',
            'contact': 'TEXT',
            'initial_balance': 'REAL DEFAULT 0',
            'remark': 'TEXT',
            'create_time': 'TEXT',
        },
        'projects': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'project_code': 'TEXT UNIQUE NOT NULL',
            'project_name': 'TEXT NOT NULL',
            'contract_no': 'TEXT',
            'customer_id': 'INTEGER',
            'start_date': 'TEXT',
            'end_date': 'TEXT',
            'remark': 'TEXT',
            'create_time': 'TEXT',
        },
        'materials': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'material_code': 'TEXT UNIQUE NOT NULL',
            'material_name': 'TEXT NOT NULL',
            'specification': 'TEXT',
            'detail_spec': 'TEXT',
            'is_national_standard': 'INTEGER DEFAULT 0',
            'brand': 'TEXT',
            'unit_id': 'INTEGER',
            'tax_price': 'REAL DEFAULT 0',
            'tax_exempt_price': 'REAL DEFAULT 0',
            'is_cash_price': 'INTEGER DEFAULT 0',
            'cash_price': 'REAL DEFAULT 0',
            'cash_tax_price': 'REAL DEFAULT 0',
            'freight': 'REAL DEFAULT 0',
            'remark': 'TEXT',
            'default_supplier_id': 'INTEGER',
            'inventory_min': 'REAL DEFAULT 0',
            'inventory_max': 'REAL DEFAULT 0',
            'tax_rate': 'REAL DEFAULT 0.01',
            'project_id': 'INTEGER',
            'weight': 'REAL DEFAULT 0',
            'create_time': 'TEXT',
        },
        'inventory': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'material_id': 'INTEGER NOT NULL',
            'warehouse_id': 'INTEGER NOT NULL',
            'quantity': 'REAL DEFAULT 0',
            'unit_price': 'REAL DEFAULT 0',
            'update_time': 'TEXT',
        },
        'base_inventory': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'material_id': 'INTEGER UNIQUE',
            'material_name': 'TEXT',
            'specification': 'TEXT',
            'detail_spec': 'TEXT',
            'unit_name': 'TEXT',
            'quantity': 'REAL DEFAULT 0',
            'unit_price': 'REAL DEFAULT 0',
            'update_time': 'TEXT',
        },
        'base_inventory_transfers': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'transfer_no': 'TEXT UNIQUE NOT NULL',
            'base_inventory_id': 'INTEGER NOT NULL',
            'project_id': 'INTEGER NOT NULL',
            'material_name': 'TEXT NOT NULL',
            'specification': 'TEXT',
            'detail_spec': 'TEXT',
            'unit_name': 'TEXT',
            'quantity': 'REAL DEFAULT 0',
            'original_unit_price': 'REAL DEFAULT 0',
            'depreciated_unit_price': 'REAL DEFAULT 0',
            'freight': 'REAL DEFAULT 0',
            'total_amount': 'REAL DEFAULT 0',
            'operator_id': 'INTEGER',
            'transfer_time': 'TEXT',
            'remark': 'TEXT',
        },
        'material_price_history': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'material_id': 'INTEGER',
            'supplier_id': 'INTEGER',
            'tax_price': 'REAL DEFAULT 0',
            'inquired_time': 'TEXT',
            'inquired_by': 'INTEGER',
            'inquiry_id': 'INTEGER',
        },
        'purchase_inquiries': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'inquiry_no': 'TEXT UNIQUE NOT NULL',
            'inquiry_date': 'TEXT',
            'applicant_id': 'INTEGER',
            'project_id': 'INTEGER',
            'total_amount': 'REAL DEFAULT 0',
            'is_below_library_price': 'INTEGER DEFAULT 0',
            'approval_status': 'TEXT DEFAULT "待审批"',
            'approval_remark': 'TEXT',
            'approver_id': 'INTEGER',
            'approve_time': 'TEXT',
            'library_price_updated': 'INTEGER DEFAULT 0',
            'create_time': 'TEXT',
            'remark': 'TEXT',
        },
        'purchase_inquiry_items': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'inquiry_id': 'INTEGER NOT NULL',
            'material_id': 'INTEGER NOT NULL',
            'quantity': 'REAL DEFAULT 1',
            'library_price': 'REAL DEFAULT 0',
            'selected_quote_id': 'INTEGER',
            'tax_rate': 'REAL DEFAULT 0.01',
            'create_time': 'TEXT',
        },
        'purchase_inquiry_quotes': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'item_id': 'INTEGER NOT NULL',
            'supplier_id': 'INTEGER NOT NULL',
            'tax_price': 'REAL DEFAULT 0',
            'tax_exempt_price': 'REAL DEFAULT 0',
            'tax_rate': 'REAL DEFAULT 0.13',
            'total_amount': 'REAL DEFAULT 0',
            'is_lowest': 'INTEGER DEFAULT 0',
            'is_selected': 'INTEGER DEFAULT 0',
            'create_time': 'TEXT',
        },
        'purchase_orders': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'order_no': 'TEXT UNIQUE NOT NULL',
            'order_type': 'TEXT DEFAULT "集采"',
            'project_id': 'INTEGER',
            'supplier_id': 'INTEGER',
            'total_amount': 'REAL DEFAULT 0',
            'applicant_id': 'INTEGER',
            'approval_status': 'TEXT DEFAULT "待审批"',
            'approval_remark': 'TEXT',
            'approver_id': 'INTEGER',
            'approve_time': 'TEXT',
            'purchase_status': 'TEXT DEFAULT "待入库"',
            'create_time': 'TEXT',
            'remark': 'TEXT',
        },
        'purchase_order_details': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'order_id': 'INTEGER',
            'material_id': 'INTEGER',
            'quantity': 'REAL DEFAULT 0',
            'unit_price': 'REAL DEFAULT 0',
            'amount': 'REAL DEFAULT 0',
            'in_quantity': 'REAL DEFAULT 0',
        },
        'stock_in_orders': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'order_no': 'TEXT UNIQUE NOT NULL',
            'source_type': 'TEXT DEFAULT "采购入库"',
            'related_order_no': 'TEXT',
            'supplier_id': 'INTEGER',
            'warehouse_id': 'INTEGER',
            'operator_id': 'INTEGER',
            'in_time': 'TEXT',
            'status': 'TEXT DEFAULT "已入库"',
            'create_time': 'TEXT',
            'remark': 'TEXT',
            'project_id': 'INTEGER',
        },
        'stock_in_details': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'order_id': 'INTEGER',
            'material_id': 'INTEGER',
            'quantity': 'REAL DEFAULT 0',
            'unit_price': 'REAL DEFAULT 0',
            'amount': 'REAL DEFAULT 0',
            'supplier_id': 'INTEGER',
        },
        'stock_out_orders': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'order_no': 'TEXT UNIQUE NOT NULL',
            'out_type': 'TEXT DEFAULT "领用"',
            'customer_name': 'TEXT',
            'warehouse_id': 'INTEGER',
            'operator_id': 'INTEGER',
            'out_time': 'TEXT',
            'create_time': 'TEXT',
            'remark': 'TEXT',
            'team_name': 'TEXT',
            'receiver_name': 'TEXT',
            'project_id': 'INTEGER',
        },
        'stock_out_details': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'order_id': 'INTEGER',
            'material_id': 'INTEGER',
            'quantity': 'REAL DEFAULT 0',
            'unit_price': 'REAL DEFAULT 0',
            'amount': 'REAL DEFAULT 0',
            'team_name': 'TEXT',
            'receiver_name': 'TEXT',
        },
        'stock_transfer_orders': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'transfer_no': 'TEXT UNIQUE NOT NULL',
            'from_warehouse_id': 'INTEGER NOT NULL',
            'to_warehouse_id': 'INTEGER NOT NULL',
            'operator_id': 'INTEGER',
            'transfer_time': 'TEXT',
            'create_time': 'TEXT',
            'remark': 'TEXT',
        },
        'stock_transfer_details': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'order_id': 'INTEGER NOT NULL',
            'material_id': 'INTEGER NOT NULL',
            'quantity': 'REAL DEFAULT 0',
            'unit_price': 'REAL DEFAULT 0',
            'amount': 'REAL DEFAULT 0',
        },
        'sales_orders': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'order_no': 'TEXT UNIQUE NOT NULL',
            'order_type': 'TEXT DEFAULT "零售"',
            'customer_id': 'INTEGER',
            'customer_name': 'TEXT',
            'total_amount': 'REAL DEFAULT 0',
            'received_amount': 'REAL DEFAULT 0',
            'payment_status': 'TEXT DEFAULT "未付款"',
            'print_count': 'INTEGER DEFAULT 0',
            'salesperson_id': 'INTEGER',
            'create_time': 'TEXT',
            'remark': 'TEXT',
        },
        'sales_order_details': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'order_id': 'INTEGER',
            'material_id': 'INTEGER',
            'quantity': 'REAL DEFAULT 0',
            'unit_price': 'REAL DEFAULT 0',
            'discount': 'REAL DEFAULT 1.0',
            'amount': 'REAL DEFAULT 0',
        },
        'reconciliation_statements': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'statement_no': 'TEXT UNIQUE NOT NULL',
            'project_id': 'INTEGER',
            'supplier_id': 'INTEGER',
            'customer_id': 'INTEGER',
            'contract_no': 'TEXT',
            'period_start': 'TEXT',
            'period_end': 'TEXT',
            'total_amount': 'REAL DEFAULT 0',
            'tax_rate': 'REAL DEFAULT 0.01',
            'tax_exempt_amount': 'REAL DEFAULT 0',
            'total_paid': 'REAL DEFAULT 0',
            'total_invoiced': 'REAL DEFAULT 0',
            'total_received': 'REAL DEFAULT 0',
            'balance_due': 'REAL DEFAULT 0',
            'status': 'TEXT DEFAULT "草稿"',
            'print_count': 'INTEGER DEFAULT 0',
            'create_time': 'TEXT',
            'remark': 'TEXT',
        },
        'reconciliation_details': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'statement_id': 'INTEGER',
            'original_no': 'TEXT',
            'transaction_date': 'TEXT',
            'material_id': 'INTEGER',
            'material_name': 'TEXT',
            'specification': 'TEXT',
            'unit_id': 'INTEGER',
            'unit_name': 'TEXT',
            'quantity': 'REAL DEFAULT 0',
            'unit_price': 'REAL DEFAULT 0',
            'amount': 'REAL DEFAULT 0',
            'remark': 'TEXT',
        },
        'approval_records': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'order_type': 'TEXT',
            'order_id': 'INTEGER',
            'approver_id': 'INTEGER',
            'approver_name': 'TEXT',
            'result': 'TEXT',
            'remark': 'TEXT',
            'approval_time': 'TEXT',
        },
        'operation_logs': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'user_id': 'INTEGER',
            'module': 'TEXT',
            'action': 'TEXT',
            'target_id': 'INTEGER',
            'detail': 'TEXT',
            'create_time': 'TEXT',
        },
    }

    fixed_count = 0

    for table_name, expected_columns in table_schemas.items():
        try:
            cursor.execute(f"PRAGMA table_info({table_name})")
            existing_columns = {row[1] for row in cursor.fetchall()}

            for col_name, col_def in expected_columns.items():
                if col_name not in existing_columns:
                    print(f"  发现缺失列: {table_name}.{col_name}")
                    try:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}")
                        print(f"    ✓ 已添加 {col_name}")
                        fixed_count += 1
                    except Exception as e:
                        print(f"    ✗ 添加失败: {e}")

        except Exception as e:
            print(f"检查表 {table_name} 失败: {e}")

    conn.commit()
    conn.close()

    if fixed_count > 0:
        print(f"数据库修复完成！共修复 {fixed_count} 个问题")
    else:
        print("数据库表结构完整，无需修复")

    return fixed_count


if __name__ == "__main__":
    auto_fix_database()
