# -*- coding: utf-8 -*-
"""
供应商名称规范化脚本
清理供应商名称，合并相似供应商
"""
import sqlite3
import re
from datetime import datetime

DB_FILE = r'h:\零星材管理系统\零星材管理系统.db'

# 手动规范化映射表
MANUAL_FIXES = {
    '永炜鑫黄建伟': ('永炜鑫', '13888137587'),
    '炜之鑫黄建伟': ('炜之鑫', '13888137587'),
    '鑫泰李福强': ('鑫泰', '13608772382'),
    '玖哲王后婵': ('玖哲', '15908714668'),
    '昆明测图仪器周': ('昆明测图仪器', '18314516646'),
    'http://e.tb.cn/h.imEuEeun5moBRME?tk=ba955f4yu7l': ('淘宝链接', None),
}

def fix_supplier_names():
    """修复供应商名称"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    print('开始修复供应商名称...\n')

    fixed_count = 0
    for old_name, (new_name, phone) in MANUAL_FIXES.items():
        # 查找并更新供应商
        cursor.execute('SELECT id, phone FROM suppliers WHERE supplier_name = ?', (old_name,))
        row = cursor.fetchone()

        if row:
            supplier_id = row[0]
            old_phone = row[1]

            # 更新名称
            cursor.execute('UPDATE suppliers SET supplier_name = ? WHERE id = ?', (new_name, supplier_id))

            # 如果有新的电话号码且原电话为空，则更新
            if phone and not old_phone:
                cursor.execute('UPDATE suppliers SET phone = ? WHERE id = ?', (phone, supplier_id))

            # 更新材料的供应商ID
            cursor.execute('''
                UPDATE materials
                SET default_supplier_id = ?
                WHERE material_code IN (
                    SELECT material_code FROM materials WHERE default_supplier_id = ?
                ) AND default_supplier_id = ?
            ''', (supplier_id, supplier_id, supplier_id))

            print(f'已修复: {old_name} -> {new_name}')
            if phone:
                print(f'  电话: {phone}')
            fixed_count += 1

    # 处理"云南富林"等只有一个手机的供应商
    # 查找所有供应商名称中包含手机号的
    cursor.execute('SELECT id, supplier_name FROM suppliers')
    for row in cursor.fetchall():
        sid, name = row
        # 提取手机号
        match = re.search(r'1[3-9]\d{9}', name)
        if match:
            phone = match.group()
            clean_name = re.sub(r'1[3-9]\d{9}', '', name).strip()
            if clean_name != name:
                # 检查是否已存在同名供应商
                cursor.execute('SELECT id FROM suppliers WHERE supplier_name = ? AND id != ?', (clean_name, sid))
                existing = cursor.fetchone()

                if existing:
                    # 合并到已有供应商
                    existing_id = existing[0]
                    cursor.execute('UPDATE materials SET default_supplier_id = ? WHERE default_supplier_id = ?', (existing_id, sid))
                    cursor.execute('DELETE FROM suppliers WHERE id = ?', (sid,))
                    print(f'合并: {name} -> {clean_name} (ID: {existing_id})')

                    # 更新已有供应商的电话
                    cursor.execute('SELECT phone FROM suppliers WHERE id = ?', (existing_id,))
                    existing_phone = cursor.fetchone()[0]
                    if not existing_phone and phone:
                        cursor.execute('UPDATE suppliers SET phone = ? WHERE id = ?', (phone, existing_id))
                else:
                    # 直接更新名称
                    cursor.execute('UPDATE suppliers SET supplier_name = ?, phone = ? WHERE id = ?', (clean_name, phone, sid))
                    print(f'已修复: {name} -> {clean_name}, 电话={phone}')

    conn.commit()

    # 显示最终结果
    cursor.execute('''
        SELECT supplier_name, phone, tax_rate, COUNT(m.id) as cnt
        FROM suppliers s
        LEFT JOIN materials m ON s.id = m.default_supplier_id
        GROUP BY s.id
        ORDER BY cnt DESC
        LIMIT 30
    ''')

    print('\n' + '=' * 60)
    print('最终供应商列表（前30个）:')
    print('=' * 60)
    for row in cursor.fetchall():
        name, phone, tax, cnt = row
        tax_str = f'{tax*100:.0f}%' if tax else '无'
        print(f'{name}: {cnt}条, 税率={tax_str}, 电话={phone or "无"}')

    print(f'\n总计: {cursor.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]} 个供应商')

    conn.close()

if __name__ == '__main__':
    fix_supplier_names()