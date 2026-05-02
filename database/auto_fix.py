"""
数据库自动修复模块
确保数据库表结构与代码定义一致
"""
import sqlite3
import config

def auto_fix_database():
    """自动检测并修复数据库表结构"""
    print("检查数据库表结构...")
    
    conn = sqlite3.connect(config.DATABASE_PATH)
    cursor = conn.cursor()
    
    # 定义所有表的列结构
    table_schemas = {
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
            'remark': 'TEXT'
        },
        'purchase_inquiry_items': {
            'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'inquiry_id': 'INTEGER NOT NULL',
            'material_id': 'INTEGER NOT NULL',
            'quantity': 'REAL DEFAULT 1',
            'library_price': 'REAL DEFAULT 0',
            'selected_quote_id': 'INTEGER',
            'tax_rate': 'REAL DEFAULT 0.01',
            'create_time': 'TEXT'
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
            'create_time': 'TEXT'
        }
    }
    
    fixed_count = 0
    
    for table_name, expected_columns in table_schemas.items():
        try:
            # 获取现有列
            cursor.execute(f"PRAGMA table_info({table_name})")
            existing_columns = {row[1] for row in cursor.fetchall()}
            
            # 检查缺失的列
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
