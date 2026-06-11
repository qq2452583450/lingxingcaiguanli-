# -*- coding: utf-8 -*-
"""
采购询价单号生成器
格式：项目编号+当天日期+序号
例如：XM001-20260501-001
"""
import sqlite3
from datetime import datetime
from database import get_connection


def generate_inquiry_no_by_project(project_id: int, date_str: str = None, exclude_id: int = None):
    """
    生成询价单号（按项目）
    格式：项目编号-日期-序号
    例如：XM001-20260501-001
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 获取项目编号
    cursor.execute("SELECT project_code FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    if not row or not row[0]:
        project_code = "XM"
    else:
        project_code = row[0]

    # 格式化日期
    if date_str:
        date_part = date_str.replace("-", "")
    else:
        date_part = datetime.now().strftime("%Y%m%d")

    # 查找当天的最大序号
    like_pattern = f"{project_code}-{date_part}-%"
    if exclude_id:
        cursor.execute(
            """
            SELECT inquiry_no FROM purchase_inquiries
            WHERE inquiry_no LIKE ? AND id != ?
            ORDER BY inquiry_no DESC LIMIT 1
            """,
            (like_pattern, exclude_id)
        )
    else:
        cursor.execute(
            "SELECT inquiry_no FROM purchase_inquiries WHERE inquiry_no LIKE ? ORDER BY inquiry_no DESC LIMIT 1",
            (like_pattern,)
        )
    row = cursor.fetchone()

    if row:
        try:
            seq_part = row[0].split("-")[-1]
            max_seq = int(seq_part)
        except:
            max_seq = 0
    else:
        max_seq = 0

    new_seq = max_seq + 1
    new_no = f"{project_code}-{date_part}-{new_seq:03d}"

    conn.close()
    return new_no


def generate_inquiry_no():
    """
    兼容旧接口：如果没有项目ID，生成通用格式
    """
    today = datetime.now().strftime("%y%m%d")
    return f"CGXJ-{today}-001"
