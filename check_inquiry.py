import sqlite3
conn = sqlite3.connect('零星材管理系统.db')
cur = conn.cursor()

# 查询询价单主表
cur.execute("SELECT id, inquiry_no, total_amount FROM purchase_inquiries WHERE inquiry_no = 'KMJJYC-20260502-001'")
print("=== 询价单主表 ===")
print(cur.fetchall())

# 查询询价单明细
cur.execute("""
    SELECT piqi.*, s.supplier_name 
    FROM purchase_inquiry_quotes piqi 
    LEFT JOIN suppliers s ON piqi.supplier_id = s.id 
    WHERE piqi.item_id IN (
        SELECT id FROM purchase_inquiry_items 
        WHERE inquiry_id = (SELECT id FROM purchase_inquiries WHERE inquiry_no = 'KMJJYC-20260502-001')
    )
""")
print("\n=== 询价单报价 ===")
for row in cur.fetchall():
    print(row)

conn.close()
