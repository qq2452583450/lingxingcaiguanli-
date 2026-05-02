# -*- coding: utf-8 -*-
import xlrd
import sqlite3
import os
import re

BASE_DIR = r'h:\零星材管理系统'
EXCEL_FILE = os.path.join(BASE_DIR, '副本零星材表格（云南直营）(2026.5.1）.xls')
DB_FILE = os.path.join(BASE_DIR, '零星材管理系统.db')

def extract_phone(text):
    """提取手机号"""
    if not text:
        return None
    # 匹配各种格式的手机号
    pattern = r'1[3-9]\d{9}'
    match = re.search(pattern, str(text))
    if match:
        return match.group()
    return None

def clean_supplier_name(name):
    """清理供应商名称，去除手机号"""
    if not name:
        return name, None
    phone = extract_phone(name)
    if phone:
        clean_name = str(name).replace(phone, '').strip()
        # 去除多余的分隔符
        clean_name = re.sub(r'[\s,，、]+$', '', clean_name)
        clean_name = re.sub(r'[\s,，]+', '', clean_name)
        return clean_name, phone
    return name, None

# 分析Excel中的供应商
wb = xlrd.open_workbook(EXCEL_FILE)
sh = wb.sheet_by_name('云南直营材料库')

suppliers_data = {}
for row_idx in range(1, sh.nrows):
    supplier = sh.cell_value(row_idx, 9)
    if supplier and isinstance(supplier, str) and supplier.strip():
        s = supplier.strip()
        if s not in suppliers_data:
            suppliers_data[s] = {'count': 0, 'phone': None}
        suppliers_data[s]['count'] += 1
        phone = extract_phone(s)
        if phone:
            suppliers_data[s]['phone'] = phone

print(f'Excel中共有 {len(suppliers_data)} 个不同的供应商\n')

# 分析需要合并的供应商
groups = {}
for name, data in suppliers_data.items():
    clean_name, phone = clean_supplier_name(name)
    if clean_name != name:
        if clean_name not in groups:
            groups[clean_name] = []
        groups[clean_name].append({'original': name, 'phone': phone, 'count': data['count']})

print(f'=== 需要合并的供应商 ({len(groups)} 组) ===\n')
for clean_name, variants in sorted(groups.items()):
    total = sum(v['count'] for v in variants)
    print(f'{clean_name}: ({total}条)')
    for v in variants:
        print(f'  - {v["original"]} ({v["count"]}条)')
    print()