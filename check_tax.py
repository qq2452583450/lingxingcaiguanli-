# -*- coding: utf-8 -*-
import re

def extract_tax_rate(text):
    """从文本中提取税率"""
    if not text:
        return None
    # 匹配 13%、13个点、13%税 等格式
    patterns = [
        r'(\d+)%',
        r'(\d+)个点',
        r'(\d+)%\s*税',
    ]
    for pattern in patterns:
        match = re.search(pattern, str(text))
        if match:
            rate = int(match.group(1))
            if rate <= 20:  # 合理的税率范围
                return rate
    return None

# 分析Excel中供应商的税率
suppliers_with_tax = {}
import xlrd
wb = xlrd.open_workbook(r'h:\零星材管理系统\副本零星材表格（云南直营）(2026.5.1）.xls')
sh = wb.sheet_by_name('云南直营材料库')

for row_idx in range(1, sh.nrows):
    supplier = sh.cell_value(row_idx, 9)
    if supplier and isinstance(supplier, str) and supplier.strip():
        s = supplier.strip()
        tax_rate = extract_tax_rate(s)
        if tax_rate:
            if s not in suppliers_with_tax:
                suppliers_with_tax[s] = tax_rate

print(f'=== 包含税率信息的供应商 ({len(suppliers_with_tax)} 个) ===\n')
for name, rate in suppliers_with_tax.items():
    print(f'{name} -> 税率: {rate}%')