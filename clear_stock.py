import sqlite3

DB_FILE = r'h:\零星材管理系统\零星材管理系统.db'

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

print('清空入库、出库、库存数据...\n')

# 清空入库相关表
tables = [
    'stock_in_orders',
    'stock_in_details',
    'stock_out_orders',
    'stock_out_details',
    'inventory',
    'material_price_history',
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
cursor.execute('SELECT COUNT(*) FROM stock_in_orders')
print(f'入库单: {cursor.fetchone()[0]} 条')
cursor.execute('SELECT COUNT(*) FROM stock_out_orders')
print(f'出库单: {cursor.fetchone()[0]} 条')
cursor.execute('SELECT COUNT(*) FROM inventory')
print(f'库存: {cursor.fetchone()[0]} 条')

conn.close()
print('\n已完成！')