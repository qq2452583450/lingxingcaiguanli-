import sqlite3

conn = sqlite3.connect(r'h:\零星材管理系统\零星材管理系统.db')
cursor = conn.cursor()

# 找出没有供应商的材料
cursor.execute('''
    SELECT id, material_code, material_name
    FROM materials
    WHERE default_supplier_id IS NULL
    LIMIT 20
''')
print('没有供应商的材料:')
for row in cursor.fetchall():
    print(f'  ID={row[0]}, Code={row[1]}, Name={row[2]}')

conn.close()