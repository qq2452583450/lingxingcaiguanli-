# -*- coding: utf-8 -*-
import sqlite3
import re

DB_FILE = r'h:\零星材管理系统\零星材管理系统.db'

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

print('开始合并供应商...\n')

# 处理所有带手机号的供应商名称
cursor.execute('SELECT id, supplier_name FROM suppliers')
all_suppliers = {row[1]: row[0] for row in cursor.fetchall()}

for name in list(all_suppliers.keys()):
    if re.search(r'1[3-9]\d{9}', name):
        phone_match = re.search(r'1[3-9]\d{9}', name)
        phone = phone_match.group()
        clean_name = re.sub(r'1[3-9]\d{9}', '', name)
        clean_name = re.sub(r'[\s\d%个点:：]+$', '', clean_name)
        clean_name = clean_name.strip()

        if clean_name != name:
            old_id = all_suppliers[name]

            if clean_name in all_suppliers:
                target_id = all_suppliers[clean_name]
                cursor.execute('UPDATE materials SET default_supplier_id = ? WHERE default_supplier_id = ?', (target_id, old_id))
                cursor.execute('DELETE FROM suppliers WHERE id = ?', (old_id,))
                print(f'合并: {name} -> {clean_name}')

                cursor.execute('SELECT phone FROM suppliers WHERE id = ?', (target_id,))
                existing_phone = cursor.fetchone()[0]
                if not existing_phone:
                    cursor.execute('UPDATE suppliers SET phone = ? WHERE id = ?', (phone, target_id))
            else:
                cursor.execute('UPDATE suppliers SET supplier_name = ?, phone = ? WHERE id = ?', (clean_name, phone, old_id))
                all_suppliers[clean_name] = old_id
                del all_suppliers[name]
                print(f'清理: {name} -> {clean_name}, 电话={phone}')

conn.commit()

# 显示结果
cursor.execute('''
    SELECT s.supplier_name, s.phone, s.tax_rate, COUNT(m.id) as cnt
    FROM suppliers s
    LEFT JOIN materials m ON s.id = m.default_supplier_id
    GROUP BY s.id
    ORDER BY cnt DESC
    LIMIT 20
''')

print('\n' + '=' * 60)
print('供应商列表（前20个）:')
print('=' * 60)
for row in cursor.fetchall():
    name, phone, tax, cnt = row
    tax_str = f'{tax*100:.0f}%' if tax else '无'
    print(f'{name}: {cnt}条, 税率={tax_str}, 电话={phone or "无"}')

cursor.execute('SELECT COUNT(*) FROM suppliers')
print(f'\n总计: {cursor.fetchone()[0]} 个供应商')

conn.close()