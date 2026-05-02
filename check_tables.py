import sqlite3
conn = sqlite3.connect('零星材管理系统.db')
cursor = conn.cursor()

# 查所有表名
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
print('所有表:', [t[0] for t in tables])

# 查 stock_out 开头的表结构
for table in ['stock_out_orders', 'stock_out_details', 'stock_out_records', 'stock_out']:
    try:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = cursor.fetchall()
        print(f'\n表 {table} 列:')
        for c in cols:
            print(f'  {c[1]} ({c[2]})')
        # 查一条数据
        cursor.execute(f"SELECT * FROM {table} LIMIT 1")
        row = cursor.fetchone()
        print(f'  示例数据: {row}')
    except Exception as e:
        print(f'\n表 {table}: {e}')

conn.close()