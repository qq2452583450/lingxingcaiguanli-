# -*- coding: utf-8 -*-
import sqlite3
import re

DB_FILE = r'h:\零星材管理系统\零星材管理系统.db'

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

print('开始合并供应商...\n')

# 定义合并规则：(原名称, 新名称, 新电话)
merges = [
    ('广发(灿宝)13658845657', '广发(灿宝)', '13658845657'),
    ('广发(灿宝)136 5884 5657', '广发(灿宝)', '13658845657'),
    ('永炜鑫黄建伟', '永炜鑫', '13888137587'),
    ('炜之鑫黄建伟', '炜之鑫', '13888137587'),
    ('鑫泰李福强', '鑫泰', '13608772382'),
    ('玖哲王后婵', '玖哲', '15908714668'),
    ('昆明测图仪器周', '昆明测图仪器', '18314516646'),
    ('http://e.tb.cn/h.imEuEeun5moBRME?tk=ba955f4yu7l', '淘宝链接', None),
    ('云南富林15198984166', '云南富林', '15198984166'),
    ('先报18287957746', '先报', '18287957746'),
    ('太原神宝玛钢15398491125', '太原神宝玛钢', '15398491125'),
    ('山西太谷神宝玛钢15398491125', '山西太谷神宝玛钢', '15398491125'),
    ('山西太谷县神宝玛钢有限公司15398491125', '山西太谷县神宝玛钢有限公司', '15398491125'),
    ('全国销售电话:13099999183', '全国销售', '13099999183'),
]

# 先处理所有带手机号的供应商名称
cursor.execute('SELECT id, supplier_name FROM suppliers')
all_suppliers = {row[1]: row[0] for row in cursor.fetchall()}

for name in list(all_suppliers.keys()):
    if re.search(r'1[3-9]\d{9}', name):
        # 提取手机号
        phone_match = re.search(r'1[3-9]\d{9}', name)
        phone = phone_match.group()

        # 提取干净名称
        clean_name = re.sub(r'1[3-9]\d{9}', '', name)
        clean_name = re.sub(r'[\s\d%个点:：]+$', '', clean_name)
        clean_name = clean_name.strip()

        if clean_name != name:
            old_id = all_suppliers[name]

            # 查找或创建目标供应商
            if clean_name in all_suppliers:
                target_id = all_suppliers[clean_name]
                # 合并材料
                cursor.execute('UPDATE materials SET default_supplier_id = ? WHERE default_supplier_id = ?', (target_id, old_id))
                # 删除旧供应商
                cursor.execute('DELETE FROM suppliers WHERE id = ?', (old_id,))
                print(f'合并: {name} -> {clean_name}')

                # 更新电话
                cursor.execute('SELECT phone FROM suppliers WHERE id = ?', (target_id,))
                existing_phone = cursor.fetchone()[0]
                if not existing_phone:
                    cursor.execute('UPDATE suppliers SET phone = ? WHERE id = ?', (phone, target_id))
            else:
                # 直接更新名称和电话
                cursor.execute('UPDATE suppliers SET supplier_name = ?, phone = ? WHERE id = ?', (clean_name, phone, old_id))
                all_suppliers[clean_name] = old_id
                del all_suppliers[name]
                print(f'清理: {name} -> {clean_name}, 电话={phone}')

conn.commit()

# 手动修复
manual_merges = [
    ('云南能赢经贸有限公司', '云南能赢经贸有限公司', None),
]

print('\n手动合并:')
for old, new, phone in manual_merges:
    cursor.execute('SELECT id FROM suppliers WHERE supplier_name LIKE ?', (f'{old}%',))
    rows = cursor.fetchall()
    if len(rows) > 1:
        main_id = rows[0][0]
        for row in rows[1:]:
            cursor.execute('UPDATE materials SET default_supplier_id = ? WHERE default_supplier_id = ?', (main_id, row[0]))
            cursor.execute('DELETE FROM suppliers WHERE id = ?', (row[0],))
        print(f'  合并多个 {old} -> ID={main_id}')

# 显示结果
cursor.execute('''
    SELECT supplier_name, phone, tax_rate, COUNT(m.id) as cnt
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