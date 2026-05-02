import sqlite3

conn = sqlite3.connect(r'h:\零星材管理系统\零星材管理系统.db')
cursor = conn.cursor()

# 查看供应商列表，按材料数量排序
cursor.execute('''
    SELECT s.supplier_name, s.phone, s.tax_rate, COUNT(m.id) as material_count
    FROM suppliers s
    LEFT JOIN materials m ON s.id = m.default_supplier_id
    GROUP BY s.id
    ORDER BY material_count DESC
    LIMIT 30
''')

print('=== 前30个供应商（按材料数量排序）===\n')
for row in cursor.fetchall():
    name, phone, tax, count = row
    tax_str = f'{tax*100:.0f}%' if tax else '无'
    print(f'{name}: {count}条材料, 税率={tax_str}, 电话={phone or "无"}')

conn.close()