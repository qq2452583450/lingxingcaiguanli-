import sqlite3
conn = sqlite3.connect('零星材管理系统.db')
cur = conn.cursor()

# 查询询价单主表
cur.execute("SELECT id, inquiry_no, total_amount FROM purchase_inquiries WHERE inquiry_no = 'KMJJYC-20260502-001'")
inquiry = cur.fetchone()
print("原数据:", inquiry)

# 查询选定的报价（is_selected=1）
cur.execute("""
    SELECT piqi.*, s.supplier_name 
    FROM purchase_inquiry_quotes piqi 
    LEFT JOIN suppliers s ON piqi.supplier_id = s.id 
    WHERE piqi.item_id IN (
        SELECT id FROM purchase_inquiry_items 
        WHERE inquiry_id = (SELECT id FROM purchase_inquiries WHERE inquiry_no = 'KMJJYC-20260502-001')
    ) AND piqi.is_selected = 1
""")
selected = cur.fetchall()
print("选定的报价:", selected)

# 计算正确的总金额
total = sum(row[6] for row in selected)  # total_amount 列
print(f"正确总金额: {total}")

# 更新
cur.execute("UPDATE purchase_inquiries SET total_amount = ? WHERE inquiry_no = 'KMJJYC-20260502-001'", (total,))
conn.commit()
print("更新完成!")

conn.close()
