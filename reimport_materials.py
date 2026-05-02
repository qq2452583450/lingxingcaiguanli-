# -*- coding: utf-8 -*-
"""
材料数据导入脚本 - 修复版
从Excel导入材料数据，正确处理供应商关联
"""
import xlrd
import sqlite3
import os
from datetime import datetime

BASE_DIR = r'h:\零星材管理系统'
EXCEL_FILE = os.path.join(BASE_DIR, '副本零星材表格（云南直营）(2026.5.1）.xls')
DB_FILE = os.path.join(BASE_DIR, '零星材管理系统.db')

def get_unit_id(conn, unit_name):
    """获取或创建计量单位ID"""
    if not unit_name or not isinstance(unit_name, str):
        unit_name = '个'
    unit_name = unit_name.strip()
    if not unit_name:
        unit_name = '个'

    cursor = conn.cursor()
    cursor.execute('SELECT id FROM units WHERE unit_name = ?', (unit_name,))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute('INSERT INTO units (unit_name) VALUES (?)', (unit_name,))
    conn.commit()
    return cursor.lastrowid

def get_supplier_id(conn, supplier_name):
    """获取或创建供应商ID"""
    if not supplier_name or not isinstance(supplier_name, str):
        return None
    supplier_name = supplier_name.strip()
    if not supplier_name:
        return None

    cursor = conn.cursor()
    cursor.execute('SELECT id FROM suppliers WHERE supplier_name = ?', (supplier_name,))
    row = cursor.fetchone()
    if row:
        return row[0]

    # 如果完全匹配找不到，尝试模糊匹配
    # 去除手机号码后匹配
    clean_name = supplier_name
    for char in '0123456789':
        clean_name = clean_name.replace(char, '')
    clean_name = clean_name.replace('-', '').replace(' ', '').replace(':', '').strip()
    if clean_name and len(clean_name) > 2:
        cursor.execute('SELECT id FROM suppliers WHERE supplier_name LIKE ?', (f'%{clean_name}%',))
        row = cursor.fetchone()
        if row:
            return row[0]

    # 创建新供应商
    cursor.execute('INSERT INTO suppliers (supplier_name, create_time) VALUES (?, ?)',
                   (supplier_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    return cursor.lastrowid

def generate_code(prefix, index):
    """生成编码，如 KMLX00001"""
    return f'{prefix}{index:05d}'

def import_materials():
    """导入材料数据"""
    print('开始重新导入材料数据...')

    # 读取Excel
    wb = xlrd.open_workbook(EXCEL_FILE)
    sh = wb.sheet_by_name('云南直营材料库')

    # 连接数据库
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 清空现有材料数据
    print('清空现有材料数据...')
    cursor.execute('DELETE FROM materials')
    cursor.execute('DELETE FROM inventory')
    conn.commit()

    # 第一次扫描：统计各类别的数量
    categories = {}
    for row_idx in range(1, sh.nrows):
        code = sh.cell_value(row_idx, 0)
        if code and isinstance(code, str) and code.strip():
            code = code.strip()
            if code not in categories:
                categories[code] = 0
            categories[code] += 1

    print(f'发现 {len(categories)} 个分类')

    # 为每个分类准备计数器
    counters = {cat: 1 for cat in categories.keys()}

    # 第二次扫描：导入数据
    imported = 0
    skipped = 0
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for row_idx in range(1, sh.nrows):
        # 列: 0-商品编号, 1-序号, 2-商品名, 3-规格, 4-单位, 5-含税价, 6-不含税价, 7-运费, 8-备注, 9-供应商
        original_code = sh.cell_value(row_idx, 0)
        name = sh.cell_value(row_idx, 2)
        specification = sh.cell_value(row_idx, 3)
        unit = sh.cell_value(row_idx, 4)
        tax_price = sh.cell_value(row_idx, 5)
        tax_exempt_price = sh.cell_value(row_idx, 6)
        freight = sh.cell_value(row_idx, 7)
        remark = sh.cell_value(row_idx, 8)
        supplier = sh.cell_value(row_idx, 9)

        if not original_code or not isinstance(original_code, str):
            skipped += 1
            continue
        original_code = original_code.strip()
        if not name or not isinstance(name, str) or not name.strip():
            skipped += 1
            continue

        # 生成新编码
        new_code = generate_code(original_code, counters[original_code])
        counters[original_code] += 1

        # 获取单位ID
        unit_id = get_unit_id(conn, unit)

        # 获取供应商ID（关键：确保正确处理）
        supplier_id = get_supplier_id(conn, supplier)

        # 处理数值
        if isinstance(tax_price, str):
            tax_price = 0
        if isinstance(tax_exempt_price, str):
            tax_exempt_price = 0
        if isinstance(freight, str):
            freight = 0

        # 插入数据
        try:
            cursor.execute('''
                INSERT INTO materials (
                    material_code, material_name, specification, unit_id,
                    tax_price, tax_exempt_price, freight, remark,
                    default_supplier_id, create_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                new_code,
                name.strip() if isinstance(name, str) else str(name),
                str(specification).strip() if specification else '',
                unit_id,
                tax_price or 0,
                tax_exempt_price or 0,
                freight or 0,
                str(remark).strip() if remark else '',
                supplier_id,
                now
            ))
            imported += 1
        except Exception as e:
            print(f'导入失败 (行{row_idx}): {e}')
            skipped += 1

    conn.commit()

    # 验证导入结果
    cursor.execute('SELECT COUNT(*) FROM materials')
    total_in_db = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM materials WHERE default_supplier_id IS NOT NULL')
    with_supplier = cursor.fetchone()[0]

    print(f'\n导入完成！')
    print(f'  成功导入: {imported} 条')
    print(f'  跳过: {skipped} 条')
    print(f'  数据库总计: {total_in_db} 条')
    print(f'  有供应商: {with_supplier} 条')
    print(f'  无供应商: {total_in_db - with_supplier} 条')

    # 显示没有供应商的材料
    if total_in_db - with_supplier > 0:
        cursor.execute('''
            SELECT material_code, material_name, specification
            FROM materials
            WHERE default_supplier_id IS NULL
            LIMIT 10
        ''')
        print('\n无供应商的材料示例:')
        for row in cursor.fetchall():
            print(f'  {row[0]}: {row[1]} ({row[2]})')

    conn.close()

if __name__ == '__main__':
    import_materials()