import sqlite3

conn = sqlite3.connect(r'h:\零星材管理系统\零星材管理系统.db')
cursor = conn.cursor()

# 检查suppliers表结构
cursor.execute("PRAGMA table_info(suppliers)")
print('供应商表结构:')
for col in cursor.fetchall():
    print(f'  {col[1]}: {col[2]}')

# 显示当前供应商示例
cursor.execute('SELECT * FROM suppliers LIMIT 5')
print('\n供应商示例:')
for row in cursor.fetchall():
    print(f'  {row}')

conn.close()