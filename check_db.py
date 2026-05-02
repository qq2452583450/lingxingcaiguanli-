import sqlite3

conn = sqlite3.connect(r'h:\零星材管理系统\零星材管理系统.db')
cursor = conn.cursor()

# 检查有供应商的材料数量
cursor.execute('''
    SELECT COUNT(*), default_supplier_id
    FROM materials
    GROUP BY default_supplier_id
''')
results = cursor.fetchall()
print('材料供应商关联情况:')
has_supplier = 0
no_supplier = 0
for count, sup_id in results:
    if sup_id:
        has_supplier += count
    else:
        no_supplier = count
        print(f'  无供应商: {count} 条')

print(f'\n有供应商: {has_supplier} 条')
print(f'无供应商: {no_supplier} 条')

# 检查供应商表中的供应商数量
cursor.execute('SELECT COUNT(*) FROM suppliers')
print(f'\n供应商表中共有 {cursor.fetchone()[0]} 个供应商')

# 显示前10个供应商
cursor.execute('SELECT supplier_name FROM suppliers ORDER BY id LIMIT 10')
print('\n前10个供应商:')
for row in cursor.fetchall():
    print(f'  {row[0]}')

conn.close()