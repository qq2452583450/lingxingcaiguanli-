"""
采购订单服务（集采）
"""
from database import get_connection
from helpers import get_now, generate_purchase_order_no


class PurchaseOrderService:
    """采购订单服务"""

    def get_all_orders(self):
        """获取所有采购订单"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT po.*, u.real_name as applicant_name,
                   s.supplier_name, p.project_name
            FROM purchase_orders po
            LEFT JOIN users u ON po.applicant_id = u.id
            LEFT JOIN suppliers s ON po.supplier_id = s.id
            LEFT JOIN projects p ON po.project_id = p.id
            ORDER BY po.create_time DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

    def get_order_by_id(self, order_id: int):
        """根据ID获取订单"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT po.*, u.real_name as applicant_name,
                   s.supplier_name, p.project_name
            FROM purchase_orders po
            LEFT JOIN users u ON po.applicant_id = u.id
            LEFT JOIN suppliers s ON po.supplier_id = s.id
            LEFT JOIN projects p ON po.project_id = p.id
            WHERE po.id = ?
        """, (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_order_details(self, order_id: int):
        """获取订单明细"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pod.*, m.material_name, m.specification,
                   u.unit_name, m.material_code
            FROM purchase_order_details pod
            LEFT JOIN materials m ON pod.material_id = m.id
            LEFT JOIN units u ON m.unit_id = u.id
            WHERE pod.order_id = ?
            ORDER BY pod.id
        """, (order_id,))
        return [dict(row) for row in cursor.fetchall()]

    def create_order(self, order_data: dict, details: list, user_id: int) -> dict:
        """创建采购订单"""
        conn = get_connection()
        cursor = conn.cursor()

        try:
            # 生成订单号
            order_no = generate_purchase_order_no()

            # 计算总金额
            total_amount = sum(d.get("unit_price", 0) * d.get("quantity", 0) for d in details)

            # 插入订单主表
            cursor.execute("""
                INSERT INTO purchase_orders (
                    order_no, order_type, project_id, supplier_id,
                    total_amount, applicant_id, approval_status,
                    purchase_status, create_time, remark
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_no, order_data.get("order_type", "集采"),
                order_data.get("project_id"), order_data.get("supplier_id"),
                total_amount, user_id, "待审批",
                "待入库", get_now(), order_data.get("remark", "")
            ))
            order_id = cursor.lastrowid

            # 插入明细
            for d in details:
                cursor.execute("""
                    INSERT INTO purchase_order_details (
                        order_id, material_id, quantity, unit_price, amount, in_quantity
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    order_id, d.get("material_id"), d.get("quantity", 0),
                    d.get("unit_price", 0), d.get("quantity", 0) * d.get("unit_price", 0), 0
                ))

            conn.commit()
            return {"success": True, "order_id": order_id, "order_no": order_no}

        except Exception as e:
            conn.rollback()
            return {"success": False, "message": str(e)}

    def approve_by_material_clerk(self, order_id: int, approver_id: int, remark: str = "") -> dict:
        """材料员审批"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE purchase_orders
            SET approval_status = '材料员已审', approver_id = ?,
                approve_time = ?, approval_remark = ?
            WHERE id = ? AND approval_status = '待审批'
        """, (approver_id, get_now(), remark, order_id))

        if cursor.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "审批失败，状态已更新"}

        cursor.execute("""
            INSERT INTO approval_records (order_type, order_id, approver_id, approver_name, result, remark, approval_time)
            SELECT 'purchase_order', ?, u.id, u.real_name, '材料员同意', ?, ?
            FROM users u WHERE u.id = ?
        """, (order_id, remark, get_now(), approver_id))

        conn.commit()
        return {"success": True}

    def approve_by_manager(self, order_id: int, approver_id: int, remark: str = "") -> dict:
        """主管审批"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE purchase_orders
            SET approval_status = '已同意', approver_id = ?,
                approve_time = ?, approval_remark = ?
            WHERE id = ? AND approval_status = '材料员已审'
        """, (approver_id, get_now(), remark, order_id))

        if cursor.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "审批失败，状态已更新"}

        cursor.execute("""
            INSERT INTO approval_records (order_type, order_id, approver_id, approver_name, result, remark, approval_time)
            SELECT 'purchase_order', ?, u.id, u.real_name, '主管同意', ?, ?
            FROM users u WHERE u.id = ?
        """, (order_id, remark, get_now(), approver_id))

        conn.commit()
        return {"success": True}

    def reject(self, order_id: int, approver_id: int, remark: str) -> dict:
        """驳回订单"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE purchase_orders
            SET approval_status = '已驳回', approver_id = ?,
                approve_time = ?, approval_remark = ?
            WHERE id = ? AND approval_status IN ('待审批', '材料员已审')
        """, (approver_id, get_now(), remark, order_id))

        if cursor.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "驳回失败，状态已更新"}

        cursor.execute("""
            INSERT INTO approval_records (order_type, order_id, approver_id, approver_name, result, remark, approval_time)
            SELECT 'purchase_order', ?, u.id, u.real_name, '驳回', ?, ?
            FROM users u WHERE u.id = ?
        """, (order_id, remark, get_now(), approver_id))

        conn.commit()
        return {"success": True}

    def update_purchase_status(self, order_id: int, status: str) -> dict:
        """更新采购状态"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE purchase_orders SET purchase_status = ? WHERE id = ?
        """, (status, order_id))
        conn.commit()
        return {"success": True}

    def delete_order(self, order_id: int) -> dict:
        """删除订单"""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT approval_status FROM purchase_orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        if not row:
            return {"success": False, "message": "订单不存在"}
        if row["approval_status"] not in ["待审批", "已驳回"]:
            return {"success": False, "message": "只有待审批或已驳回的订单才能删除"}

        cursor.execute("DELETE FROM purchase_order_details WHERE order_id = ?", (order_id,))
        cursor.execute("DELETE FROM purchase_orders WHERE id = ?", (order_id,))
        conn.commit()
        return {"success": True}
