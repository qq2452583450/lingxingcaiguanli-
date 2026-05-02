import sqlite3

DB_FILE = r'h:\零星材管理系统\零星材管理系统.db'

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# 查看仓库表结构
print('=== 仓库表 ===')
cursor.execute("SELECT * FROM warehouses LIMIT 5")
for row in cursor.fetchall():
    print(row)

# 查看项目表结构
print('\n=== 项目表 ===')
cursor.execute("SELECT id, project_code, project_name FROM projects LIMIT 5")
for row in cursor.fetchall():
    print(row)

# 查看库存表结构
print('\n=== 库存表 ===')
cursor.execute("PRAGMA table_info(inventory)")
for col in cursor.fetchall():
    print(col)

conn.close()