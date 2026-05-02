# -*- coding: utf-8 -*-
import xlrd
import os

BASE_DIR = r'h:\零星材管理系统'
EXCEL_FILE = os.path.join(BASE_DIR, '副本零星材表格（云南直营）(2026.5.1）.xls')

# 需要检查的材料名称
materials_to_check = [
    '印油', '便利贴', '门禁系统', '立式热水表', '文件柜', '防尘网',
    '兜网', '踢脚板', '内丝直接', '外丝直接', '外丝弯头',
    '通丝螺杆', '椅子', '饮水机', 'A4打印纸'
]

wb = xlrd.open_workbook(EXCEL_FILE)
sh = wb.sheet_by_name('云南直营材料库')

print('=== 检查这些材料在Excel中的供应商数据 ===\n')

found = 0
for row_idx in range(1, sh.nrows):
    name = sh.cell_value(row_idx, 2)
    if name and isinstance(name, str):
        name = name.strip()
        for mat in materials_to_check:
            if mat in name or name in mat:
                supplier = sh.cell_value(row_idx, 9)
                spec = sh.cell_value(row_idx, 3)
                print(f'材料: {name}')
                print(f'  规格: {spec}')
                print(f'  供应商: {supplier}')
                print()
                found += 1
                break

print(f'\n共找到 {found} 条匹配记录')