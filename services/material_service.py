"""
材料服务
"""
from database import get_connection
from helpers import get_now, generate_material_code
from database.models import Material


class MaterialService:
    """材料服务"""

    def get_all_materials(self):
        """获取所有材料"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.*, u.unit_name, s.supplier_name
            FROM materials m
            LEFT JOIN units u ON m.unit_id = u.id
            LEFT JOIN suppliers s ON m.default_supplier_id = s.id
            ORDER BY m.material_code
        """)
        return [dict(row) for row in cursor.fetchall()]

    def get_material_by_id(self, material_id: int):
        """根据ID获取材料"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.*, u.unit_name, s.supplier_name
            FROM materials m
            LEFT JOIN units u ON m.unit_id = u.id
            LEFT JOIN suppliers s ON m.default_supplier_id = s.id
            WHERE m.id = ?
        """, (material_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def search_materials(self, keyword: str):
        """搜索材料（按名称、编码、规格）"""
        conn = get_connection()
        cursor = conn.cursor()
        like = f"%{keyword}%"
        cursor.execute("""
            SELECT m.*, u.unit_name, s.supplier_name
            FROM materials m
            LEFT JOIN units u ON m.unit_id = u.id
            LEFT JOIN suppliers s ON m.default_supplier_id = s.id
            WHERE m.material_name LIKE ? OR m.material_code LIKE ? OR m.specification LIKE ?
            ORDER BY m.material_code
        """, (like, like, like))
        return [dict(row) for row in cursor.fetchall()]

    def add_material(self, material: Material) -> dict:
        """添加材料"""
        conn = get_connection()
        cursor = conn.cursor()

        # 生成材料编码
        material_code = generate_material_code()

        # 计算不含税价（简化处理：含税价 / 1.01）
        if material.tax_price and not material.tax_exempt_price:
            material.tax_exempt_price = round(material.tax_price / 1.01, 2)

        cursor.execute("""
            INSERT INTO materials (
                material_code, material_name, specification, unit_id,
                tax_price, tax_exempt_price, freight, remark,
                default_supplier_id, inventory_min, inventory_max, create_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            material_code, material.material_name, material.specification,
            material.unit_id, material.tax_price, material.tax_exempt_price,
            material.freight, material.remark, material.default_supplier_id,
            material.inventory_min, material.inventory_max, get_now()
        ))
        conn.commit()
        return {"success": True, "material_code": material_code}

    def update_material(self, material: Material) -> dict:
        """更新材料"""
        conn = get_connection()
        cursor = conn.cursor()

        # 计算不含税价
        if material.tax_price and not material.tax_exempt_price:
            material.tax_exempt_price = round(material.tax_price / 1.01, 2)

        cursor.execute("""
            UPDATE materials SET
                material_name = ?, specification = ?, unit_id = ?,
                tax_price = ?, tax_exempt_price = ?, freight = ?, remark = ?,
                default_supplier_id = ?, inventory_min = ?, inventory_max = ?
            WHERE id = ?
        """, (
            material.material_name, material.specification, material.unit_id,
            material.tax_price, material.tax_exempt_price, material.freight,
            material.remark, material.default_supplier_id,
            material.inventory_min, material.inventory_max, material.id
        ))
        conn.commit()
        return {"success": True}

    def delete_material(self, material_id: int) -> dict:
        """删除材料"""
        conn = get_connection()
        cursor = conn.cursor()

        # 检查是否被引用
        cursor.execute("SELECT COUNT(*) FROM purchase_inquiry_details WHERE material_id = ?", (material_id,))
        if cursor.fetchone()[0] > 0:
            return {"success": False, "message": "该材料已被询价单引用，无法删除"}

        cursor.execute("DELETE FROM materials WHERE id = ?", (material_id,))
        conn.commit()
        return {"success": True}

    def update_library_price(self, material_id: int, new_price: float):
        """更新库内含税价"""
        conn = get_connection()
        cursor = conn.cursor()
        tax_exempt = round(new_price / 1.01, 2)
        cursor.execute("""
            UPDATE materials SET tax_price = ?, tax_exempt_price = ? WHERE id = ?
        """, (new_price, tax_exempt, material_id))
        conn.commit()
