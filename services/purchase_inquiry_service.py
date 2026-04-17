"""
采购询价服务
"""
from database import get_connection
from helpers import get_now, generate_inquiry_no


class PurchaseInquiryService:
    """采购询价服务"""

    def get_all_inquiries(self):
        """获取所有询价单"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pi.*, u.real_name as applicant_name,
                   CASE pi.approval_status
                       WHEN '待审批' THEN '待材料员审批'
                       WHEN '材料员已审' THEN '待主管审批'
                       ELSE pi.approval_status
                   END as status_desc
            FROM purchase_inquiries pi
            LEFT JOIN users u ON pi.applicant_id = u.id
            ORDER BY pi.create_time DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

    def get_inquiry_by_id(self, inquiry_id: int):
        """根据ID获取询价单"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pi.*, u.real_name as applicant_name
            FROM purchase_inquiries pi
            LEFT JOIN users u ON pi.applicant_id = u.id
            WHERE pi.id = ?
        """, (inquiry_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_inquiry_details(self, inquiry_id: int):
        """获取询价单明细"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pd.*, m.material_name, m.specification, m.material_code,
                   u.unit_name, s.supplier_name
            FROM purchase_inquiry_details pd
            LEFT JOIN materials m ON pd.material_id = m.id
            LEFT JOIN units u ON m.unit_id = u.id
            LEFT JOIN suppliers s ON pd.supplier_id = s.id
            WHERE pd.inquiry_id = ?
            ORDER BY pd.id
        """, (inquiry_id,))
        return [dict(row) for row in cursor.fetchall()]

    def create_inquiry(self, inquiry_data: dict, details: list, user_id: int) -> dict:
        """创建询价单"""
        conn = get_connection()
        cursor = conn.cursor()

        try:
            # 生成询价单号
            inquiry_no = generate_inquiry_no()

            # 计算总金额
            total_amount = sum(d.get("this_price", 0) * d.get("quantity", 1) for d in details)

            # 检查是否低于库内价
            is_below_library = 0
            for d in details:
                if d.get("this_price", 0) < d.get("library_price", 0):
                    is_below_library = 1
                    break

            # 插入询价单主表
            cursor.execute("""
                INSERT INTO purchase_inquiries (
                    inquiry_no, inquiry_date, applicant_id, total_amount,
                    is_below_library_price, approval_status, create_time, remark
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                inquiry_no, inquiry_data.get("inquiry_date", get_now()[:10]),
                user_id, total_amount, is_below_library, "待审批",
                get_now(), inquiry_data.get("remark", "")
            ))
            inquiry_id = cursor.lastrowid

            # 插入明细
            for d in details:
                material_id = d.get("material_id")
                supplier_id = d.get("supplier_id")
                this_price = d.get("this_price", 0)
                library_price = d.get("library_price", 0)
                quantity = d.get("quantity", 1)

                # 判断是否最低价
                is_lowest = 1 if this_price <= library_price else 0
                price_diff = this_price - library_price

                cursor.execute("""
                    INSERT INTO purchase_inquiry_details (
                        inquiry_id, material_id, supplier_id, this_price,
                        library_price, is_lowest, price_diff, quantity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (inquiry_id, material_id, supplier_id, this_price,
                      library_price, is_lowest, price_diff, quantity))

            conn.commit()
            return {"success": True, "inquiry_id": inquiry_id, "inquiry_no": inquiry_no}

        except Exception as e:
            conn.rollback()
            return {"success": False, "message": str(e)}

    def approve_by_material_clerk(self, inquiry_id: int, approver_id: int, remark: str = "") -> dict:
        """材料员审批"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE purchase_inquiries
            SET approval_status = '材料员已审', approver_id = ?,
                approve_time = ?, approval_remark = ?
            WHERE id = ? AND approval_status = '待审批'
        """, (approver_id, get_now(), remark, inquiry_id))

        if cursor.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "审批失败，状态已更新"}

        # 记录审批
        cursor.execute("""
            INSERT INTO approval_records (order_type, order_id, approver_id, approver_name, result, remark, approval_time)
            SELECT 'purchase_inquiry', ?, u.id, u.real_name, '材料员同意', ?, ?
            FROM users u WHERE u.id = ?
        """, (inquiry_id, remark, get_now(), approver_id))

        conn.commit()
        return {"success": True}

    def approve_by_manager(self, inquiry_id: int, approver_id: int, remark: str = "") -> dict:
        """主管审批"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE purchase_inquiries
            SET approval_status = '已同意', approver_id = ?,
                approve_time = ?, approval_remark = ?
            WHERE id = ? AND approval_status = '材料员已审'
        """, (approver_id, get_now(), remark, inquiry_id))

        if cursor.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "审批失败，状态已更新"}

        # 记录审批
        cursor.execute("""
            INSERT INTO approval_records (order_type, order_id, approver_id, approver_name, result, remark, approval_time)
            SELECT 'purchase_inquiry', ?, u.id, u.real_name, '主管同意', ?, ?
            FROM users u WHERE u.id = ?
        """, (inquiry_id, remark, get_now(), approver_id))

        conn.commit()
        return {"success": True}

    def reject(self, inquiry_id: int, approver_id: int, remark: str) -> dict:
        """驳回询价单"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE purchase_inquiries
            SET approval_status = '已驳回', approver_id = ?,
                approve_time = ?, approval_remark = ?
            WHERE id = ? AND approval_status IN ('待审批', '材料员已审')
        """, (approver_id, get_now(), remark, inquiry_id))

        if cursor.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "驳回失败，状态已更新"}

        # 记录审批
        cursor.execute("""
            INSERT INTO approval_records (order_type, order_id, approver_id, approver_name, result, remark, approval_time)
            SELECT 'purchase_inquiry', ?, u.id, u.real_name, '驳回', ?, ?
            FROM users u WHERE u.id = ?
        """, (inquiry_id, remark, get_now(), approver_id))

        conn.commit()
        return {"success": True}

    def update_library_price(self, inquiry_id: int) -> dict:
        """更新库内价"""
        conn = get_connection()
        cursor = conn.cursor()

        # 检查是否已同意
        cursor.execute("SELECT approval_status FROM purchase_inquiries WHERE id = ?", (inquiry_id,))
        row = cursor.fetchone()
        if not row or row["approval_status"] != "已同意":
            return {"success": False, "message": "只有已审批通过的询价单才能更新库内价"}

        # 获取明细
        details = self.get_inquiry_details(inquiry_id)
        for d in details:
            if d.get("is_lowest") == 1:
                # 更新库内价
                cursor.execute("""
                    UPDATE materials SET tax_price = ?, tax_exempt_price = ?
                    WHERE id = ?
                """, (d["this_price"], round(d["this_price"] / 1.01, 2), d["material_id"]))

        # 标记已更新
        cursor.execute("""
            UPDATE purchase_inquiries SET library_price_updated = 1 WHERE id = ?
        """, (inquiry_id,))

        conn.commit()
        return {"success": True}

    def delete_inquiry(self, inquiry_id: int) -> dict:
        """删除询价单"""
        conn = get_connection()
        cursor = conn.cursor()

        # 检查状态
        cursor.execute("SELECT approval_status FROM purchase_inquiries WHERE id = ?", (inquiry_id,))
        row = cursor.fetchone()
        if not row:
            return {"success": False, "message": "询价单不存在"}
        if row["approval_status"] not in ["待审批", "已驳回"]:
            return {"success": False, "message": "只有待审批或已驳回的询价单才能删除"}

        # 删除明细
        cursor.execute("DELETE FROM purchase_inquiry_details WHERE inquiry_id = ?", (inquiry_id,))
        # 删除主表
        cursor.execute("DELETE FROM purchase_inquiries WHERE id = ?", (inquiry_id,))

        conn.commit()
        return {"success": True}
