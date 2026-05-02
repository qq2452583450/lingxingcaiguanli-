# -*- coding: utf-8 -*-
import xlrd
import os

BASE_DIR = r'h:\零星材管理系统'
EXCEL_FILE = os.path.join(BASE_DIR, '副本零星材表格（云南直营）(2026.5.1）.xls')

def analyze_suppliers():
    """分析供应商数据"""
    wb = xlrd.open_workbook(EXCEL_FILE)
    sh = wb.sheet_by_name('云南直营材料库')

    print('=== 分析供应商数据 ===\n')

    # 检查第10列（索引9）是供应商列
    suppliers = {}
    empty_count = 0
    total = 0

    for row_idx in range(1, sh.nrows):
        name = sh.cell_value(row_idx, 2)  # 商品名
        supplier = sh.cell_value(row_idx, 9)  # 供应商列
        col0 = sh.cell_value(row_idx, 0)  # 分类代码

        if col0 and isinstance(col0, str) and col0.strip():
            if name and isinstance(name, str) and name.strip():
                total += 1
                if supplier and isinstance(supplier, str) and supplier.strip():
                    sup = supplier.strip()
                    if sup not in suppliers:
                        suppliers[sup] = 0
                    suppliers[sup] += 1
                else:
                    empty_count += 1

    print(f'总材料数: {total}')
    print(f'有供应商: {total - empty_count}')
    print(f'无供应商: {empty_count}')

    print(f'\n供应商列表 ({len(suppliers)} 个):')
    for sup, count in sorted(suppliers.items(), key=lambda x: -x[1]):
        print(f'  {sup}: {count} 条')

    # 检查列10（索引10）是否有供应商数据
    print('\n\n=== 检查其他列的供应商数据 ===')
    suppliers_col10 = {}
    for row_idx in range(1, min(100, sh.nrows)):
        name = sh.cell_value(row_idx, 2)
        supplier_col10 = sh.cell_value(row_idx, 10)
        if name and isinstance(name, str) and name.strip():
            if supplier_col10 and isinstance(supplier_col10, str) and supplier_col10.strip():
                sup = supplier_col10.strip()
                if sup not in suppliers_col10:
                    suppliers_col10[sup] = 0
                suppliers_col10[sup] += 1

    print(f'第11列(索引10)有 {len(suppliers_col10)} 个供应商')
    for sup, count in list(suppliers_col10.items())[:20]:
        print(f'  {sup}: {count}')

if __name__ == '__main__':
    analyze_suppliers()