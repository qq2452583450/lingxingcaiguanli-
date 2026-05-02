# -*- coding: utf-8 -*-
"""
供应商和材料数据导入脚本
规范化处理供应商名称，合并相似供应商
"""
import xlrd
import sqlite3
import os
import re
from datetime import datetime

BASE_DIR = r'h:\零星材管理系统'
EXCEL_FILE = os.path.join(BASE_DIR, '副本零星材表格（云南直营）(2026.5.1）.xls')
DB_FILE = os.path.join(BASE_DIR, '零星材管理系统.db')

def extract_phone(text):
    """提取手机号"""
    if not text:
        return None
    pattern = r'1[3-9]\d{9}'
    match = re.search(pattern, str(text))
    return match.group() if match else None

def extract_tax_rate(text):
    """从文本中提取税率"""
    if not text:
        return None
    patterns = [r'(\d+)%', r'(\d+)个点']
    for pattern in patterns:
        match = re.search(pattern, str(text))
        if match:
            rate = int(match.group(1))
            if rate <= 20:
                return rate
    return None

def clean_supplier_name(name):
    """清理供应商名称，去除手机号、税率等信息"""
    if not name:
        return name, None, None

    phone = extract_phone(name)
    tax_rate = extract_tax_rate(name)

    clean_name = str(name)
    # 去除手机号
    if phone:
        clean_name = clean_name.replace(phone, '')
    # 去除税率信息
    clean_name = re.sub(r'\d+%\s*税', '', clean_name)
    clean_name = re.sub(r'\d+个点', '', clean_name)
    clean_name = re.sub(r'\d+%', '', clean_name)
    # 去除多余分隔符
    clean_name = re.sub(r'[\s,，、:：]+', '', clean_name)
    clean_name = re.sub(r'\s+', '', clean_name)
    clean_name = clean_name.strip()

    # 处理特殊格式
    if clean_name.endswith('代'):
        clean_name = clean_name[:-1]
    if clean_name.endswith('电话'):
        clean_name = clean_name[:-2]
    if clean_name.startswith('全国'):
        clean_name = '全国销售'

    return clean_name if clean_name else name, phone, tax_rate

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

def get_supplier_id(conn, supplier_name, phone=None, tax_rate=None):
    """获取或创建供应商ID（带规范化处理）"""
    if not supplier_name or not isinstance(supplier_name, str):
        return None
    supplier_name = supplier_name.strip()
    if not supplier_name:
        return None

    # 清理名称
    clean_name, extracted_phone, extracted_tax = clean_supplier_name(supplier_name)
    phone = phone or extracted_phone
    tax_rate = tax_rate or extracted_tax

    cursor = conn.cursor()

    # 先查找已存在的供应商（模糊匹配）
    cursor.execute('''
        SELECT id, supplier_name, phone, tax_rate
        FROM suppliers
        WHERE supplier_name = ? OR supplier_name LIKE ?
    ''', (clean_name, f'%{clean_name[:4]}%'))

    for row in cursor.fetchall():
        existing_name = row[1]
        existing_clean, _, _ = clean_supplier_name(existing_name)
        if existing_clean == clean_name:
            # 更新手机和税率
            if phone and not row[2]:
                cursor.execute('UPDATE suppliers SET phone = ? WHERE id = ?', (phone, row[0]))
            if tax_rate and not row[3]:
                cursor.execute('UPDATE suppliers SET tax_rate = ? WHERE id = ?', (tax_rate / 100, row[0]))
            conn.commit()
            return row[0]

    # 创建新供应商
    cursor.execute('''
        INSERT INTO suppliers (supplier_name, phone, tax_rate, create_time)
        VALUES (?, ?, ?, ?)
    ''', (clean_name, phone, tax_rate / 100 if tax_rate else None, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    return cursor.lastrowid

def generate_code(prefix, index):
    """生成编码，如 KMLX00001"""
    return f'{prefix}{index:05d}'

def add_tax_rate_column(conn):
    """添加税率字段"""
    cursor = conn.cursor()
    try:
        cursor.execute('ALTER TABLE suppliers ADD COLUMN tax_rate REAL')
        conn.commit()
    except:
        pass

def import_materials():
    """导入材料数据"""
    print('=' * 60)
    print('开始导入供应商和材料数据...')
    print('=' * 60)

    # 读取Excel
    wb = xlrd.open_workbook(EXCEL_FILE)
    sh = wb.sheet_by_name('云南直营材料库')

    # 连接数据库
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 添加税率字段
    print('\n[1/4] 添加税率字段...')
    add_tax_rate_column(conn)

    # 清空现有数据
    print('[2/4] 清空现有材料数据...')
    cursor.execute('DELETE FROM materials')
    cursor.execute('DELETE FROM inventory')
    # 清空现有供应商
    cursor.execute('DELETE FROM suppliers')
    conn.commit()

    # 第一次扫描：统计各类别的数量
    print('[3/4] 分析材料数据...')
    categories = {}
    for row_idx in range(1, sh.nrows):
        code = sh.cell_value(row_idx, 0)
        if code and isinstance(code, str) and code.strip():
            code = code.strip()
            if code not in categories:
                categories[code] = 0
            categories[code] += 1

    print(f'  发现 {len(categories)} 个分类，共 {sum(categories.values())} 条材料')

    # 为每个分类准备计数器
    counters = {cat: 1 for cat in categories.keys()}

    # 统计供应商
    supplier_stats = {}

    # 第二次扫描：导入数据
    print('[4/4] 导入材料数据...')
    imported = 0
    skipped = 0
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for row_idx in range(1, sh.nrows):
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

        # 获取供应商ID
        supplier_id = get_supplier_id(conn, supplier)
        if supplier and isinstance(supplier, str):
            clean_name, _, _ = clean_supplier_name(supplier)
            if clean_name not in supplier_stats:
                supplier_stats[clean_name] = 0
            supplier_stats[clean_name] += 1

        # 处理数值
        if isinstance(tax_price, str):
            tax_price = 0
        if isinstance(tax_exempt_price, str):
            tax_exempt_price = 0
        if isinstance(freight, str):
            freight = 0

        try:
            cursor.execute('''
                INSERT INTO materials (
                    material_code, material_name, specification, unit_id,
                    tax_price, tax_exempt_price, freight, remark,
                    default_supplier_id, create_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                new_code,
                name.strip(),
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

    # 输出结果
    cursor.execute('SELECT COUNT(*) FROM materials')
    total_materials = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM materials WHERE default_supplier_id IS NOT NULL')
    with_supplier = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM suppliers')
    total_suppliers = cursor.fetchone()[0]

    cursor.execute('SELECT supplier_name, phone, tax_rate FROM suppliers WHERE phone IS NOT NULL OR tax_rate IS NOT NULL')
    suppliers_with_extra = cursor.fetchall()

    print('\n' + '=' * 60)
    print('导入完成！')
    print('=' * 60)
    print(f'  材料总数: {total_materials} 条')
    print(f'  有供应商: {with_supplier} 条')
    print(f'  无供应商: {total_materials - with_supplier} 条')
    print(f'  供应商数: {total_suppliers} 个')
    print(f'  有电话/税率: {len(suppliers_with_extra)} 个')

    print('\n有税率信息的供应商:')
    for row in suppliers_with_extra:
        if row[2]:
            print(f'  {row[0]}: 税率={row[2]*100:.0f}%, 电话={row[1] or "无"}')

    conn.close()

if __name__ == '__main__':
    import_materials()