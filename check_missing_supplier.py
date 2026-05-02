import sqlite3
import xlrd
import os

BASE_DIR = r'h:\零星材管理系统'
EXCEL_FILE = os.path.join(BASE_DIR, '副本零星材表格（云南直营）(2026.5.1）.xls')
DB_FILE = os.path.join(BASE_DIR, '零星材管理系统.db')

# 获取数据库中的供应商列表
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()
cursor.execute('SELECT supplier_name FROM suppliers')
db_suppliers = set(row[0] for row in cursor.fetchall())
conn.close()

print(f'数据库中有 {len(db_suppliers)} 个供应商')

# 从Excel获取供应商列表
wb = xlrd.open_workbook(EXCEL_FILE)
sh = wb.sheet_by_name('云南直营材料库')
excel_suppliers = set()
for row_idx in range(1, sh.nrows):
    supplier = sh.cell_value(row_idx, 9)
    if supplier and isinstance(supplier, str) and supplier.strip():
        excel_suppliers.add(supplier.strip())

print(f'Excel中有 {len(excel_suppliers)} 个供应商')

# 找出Excel中有但数据库中没有的供应商
missing = excel_suppliers - db_suppliers
print(f'\nExcel中有但数据库中没有的供应商 ({len(missing)} 个):')
for sup in sorted(missing):
    print(f'  {sup}')