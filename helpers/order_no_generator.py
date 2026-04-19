"""
单号生成器
"""
import sqlite3
from datetime import datetime
from database import get_connection


def generate_order_no(prefix: str, date_format: str = "%y%m%d", seq_digits: int = 3, max_retries: int = 10):
    """
    生成单号（带重试机制防止并发冲突）
    """
    conn = get_connection()
    cursor = conn.cursor()

    today = datetime.now().strftime(date_format)
    seq_digit_str = "{" + f"0:0{seq_digits}d" + "}"

    tables_with_no = [
        ("stock_in_orders", "order_no"),
        ("stock_out_orders", "order_no"),
        ("sales_orders", "order_no"),
        ("purchase_inquiries", "inquiry_no"),
    ]

    for attempt in range(max_retries):
        # 每次重试时重新计算最大序号
        like_pattern = f"{prefix}-{today}-%"
        max_seq = 0
        for table, col in tables_with_no:
            cursor.execute(
                f"SELECT {col} FROM {table} WHERE {col} LIKE ? ORDER BY {col} DESC LIMIT 1",
                (like_pattern,)
            )
            row = cursor.fetchone()
            if row:
                last_no = row[0]
                try:
                    seq_part = last_no.split("-")[-1]
                    seq = int(seq_part)
                    if seq > max_seq:
                        max_seq = seq
                except:
                    pass

        new_seq = max_seq + 1
        new_no = f"{prefix}-{today}-{seq_digit_str.format(new_seq)}"

        # 检查是否已存在
        cursor.execute("SELECT 1 FROM purchase_inquiries WHERE inquiry_no = ?", (new_no,))
        if not cursor.fetchone():
            conn.close()
            return new_no

        # 已存在，尝试下一个序号（继续循环）

    conn.close()
    raise Exception(f"无法生成唯一的单号，已重试{max_retries}次")


def generate_inquiry_no():
    """生成询价单号 CGXJ-YYMMDD-XXX"""
    return generate_order_no("CGXJ", "%y%m%d", 3)


def generate_stock_in_no():
    """生成入库单号 JH-YYMMDD-XXX"""
    return generate_order_no("JH", "%y%m%d", 3)


def generate_stock_out_no():
    """生成出库单号 CK-YYMMDD-XXX"""
    return generate_order_no("CK", "%y%m%d", 3)


def generate_sales_no():
    """生成销售单号 XS-YYMMDD-XXXX"""
    return generate_order_no("XS", "%y%m%d", 4)


def generate_purchase_order_no():
    """生成采购单号 CGDD-YYMMDD-XXX"""
    return generate_order_no("CGDD", "%y%m%d", 3)


def generate_reconciliation_no(period_start: str, period_end: str):
    """
    生成对账单编号 DZD-YYYY.N.N~YYYY.N.N
    period_start/period_end 格式如 2026-01-01
    """
    # 简化： DZD-2026.1.1~2026.1.15
    try:
        start = datetime.strptime(period_start, "%Y-%m-%d")
        end = datetime.strptime(period_end, "%Y-%m-%d")
        start_str = f"{start.year}.{start.month}.{start.day}"
        end_str = f"{end.year}.{end.month}.{end.day}"
        return f"DZD-{start_str}~{end_str}"
    except:
        return f"DZD-{period_start}~{period_end}"


def generate_material_code():
    """生成材料编码"""
    conn = get_connection()
    cursor = conn.cursor()

    # 查找最大的材料编码
    cursor.execute("SELECT material_code FROM materials ORDER BY material_code DESC LIMIT 1")
    row = cursor.fetchone()

    if row:
        last_code = row[0]
        # 假设格式为 BNLX-001 之类的
        try:
            prefix = last_code.split("-")[0]
            num = int(last_code.split("-")[1])
            new_num = num + 1
            return f"{prefix}-{new_num:03d}"
        except:
            pass

    # 默认从 BNLX-001 开始
    return "BNLX-001"
