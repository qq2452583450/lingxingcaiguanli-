# -*- coding: utf-8 -*-
import xlrd
import os

BASE_DIR = r'h:\零星材管理系统'
EXCEL_FILE = os.path.join(BASE_DIR, '副本零星材表格（云南直营）(2026.5.1）.xls')

# 需要检查的材料编码
codes_to_check = [
    'YXLX00026', 'YXLX00027', 'YXLX00028', 'KMLX01026', 'DLLX01150',
    'YXLX00033', 'YXLX00034', 'KMJDLX00105', 'KMJDLX00106', 'YXLX00088',
    'YXLX00089', 'YXLX00090', 'KMLX01587', 'KMLX01701', 'KMLX01702', 'KMLX01703'
]

wb = xlrd.open_workbook(EXCEL_FILE)
sh = wb.sheet_by_name('云南直营材料库')

print('=== 检查这些材料在Excel中的原始数据 ===\n')

found = 0
for row_idx in range(1, sh.nrows):
    name = sh.cell_value(row_idx, 2)
    supplier = sh.cell_value(row_idx, 9)
    spec = sh.cell_value(row_idx, 3)

    if name and isinstance(name, str) and name.strip():
        # 查找匹配的材料（通过序号）
        seq = sh.cell_value(row_idx, 1)
        if isinstance(seq, float):
            # 根据分类生成新编码
            code = sh.cell_value(row_idx, 0)
            if code and isinstance(code, str) and code.strip():
                # 根据分类计算序号
                pass

# 更直接的方法：直接搜索材料名称
print('按名称搜索:')
materials_found = {}
for row_idx in range(1, sh.nrows):
    name = sh.cell_value(row_idx, 2)
    supplier = sh.cell_value(row_idx, 9)
    code = sh.cell_value(row_idx, 0)

    if name and isinstance(name, str):
        name = name.strip()
        for target in ['印油', '便利贴', '门禁系统', '立式热水表', '文件柜', '防尘网',
                       '兜网', '踢脚板', '内丝直接', '外丝直接', '外丝弯头',
                       '通丝螺杆', '椅子', '饮水机', 'A4打印纸']:
            if name == target:
                key = f'{name}_{spec}' if spec else name
                if key not in materials_found:
                    materials_found[key] = supplier
                break

for mat, sup in materials_found.items():
    print(f'  {mat}: {sup if sup else "无供应商"}')