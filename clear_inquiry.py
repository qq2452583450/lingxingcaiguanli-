import sqlite3

DB_FILE = r'h:\零星材管理系统\零星材管理系统.db'

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

print('清空采购询比价数据...\n')

tables = [
    'purchase_inquiry_items',
    'purchase_inquiry_quotes',
    'purchase_inquiry_details',
    'purchase_inquiries',
    'approval_records',
]

for table in tables:
    try:
        cursor.execute(f'DELETE FROM {table}')
        print(f'已清空: {table}')
    except Exception as e:
        print(f'清空 {table} 失败: {e}')

conn.commit()

# 验证
print('\n验证结果:')
cursor.execute('SELECT COUNT(*) FROM purchase_inquiries')
print(f'询价单: {cursor.fetchone()[0]} 条')

conn.close()
print('\n已完成！')