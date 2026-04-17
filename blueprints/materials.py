"""
材料管理蓝图
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime
from html import escape
from helpers import get_db

material_bp = Blueprint('materials', __name__, url_prefix='/api')


@material_bp.route('/materials', methods=['GET'])
def get_materials():
    """获取材料列表（支持分页和搜索）"""
    keyword = request.args.get('keyword', '')
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    offset = (page - 1) * page_size

    conn = get_db()
    cursor = conn.cursor()

    # 构建 WHERE 条件
    where_clause = ''
    params = []
    if keyword:
        like = f'%{keyword}%'
        where_clause = 'WHERE (m.material_name LIKE ? OR m.material_code LIKE ? OR m.specification LIKE ?)'
        params = [like, like, like]

    # 查询总数
    count_sql = f'SELECT COUNT(*) FROM materials m {where_clause}'
    cursor.execute(count_sql, params)
    total = cursor.fetchone()[0]

    # 查询分页数据
    sql = f"""
        SELECT m.*, u.unit_name, s.supplier_name
        FROM materials m
        LEFT JOIN units u ON m.unit_id = u.id
        LEFT JOIN suppliers s ON m.default_supplier_id = s.id
        {where_clause}
        ORDER BY m.material_code
        LIMIT ? OFFSET ?
    """
    params.extend([page_size, offset])
    cursor.execute(sql, params)
    materials = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        'success': True,
        'data': materials,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size
    })


@material_bp.route('/materials/<int:material_id>', methods=['GET'])
def get_material(material_id):
    """获取单个材料"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.*, u.unit_name, s.supplier_name
        FROM materials m
        LEFT JOIN units u ON m.unit_id = u.id
        LEFT JOIN suppliers s ON m.default_supplier_id = s.id
        WHERE m.id = ?
    """, (material_id,))
    row = cursor.fetchone()
    conn.close()
    material = dict(row) if row else None
    return jsonify({'success': True, 'data': material})


@material_bp.route('/materials', methods=['POST'])
def create_material():
    """创建材料"""
    data = request.json
    conn = get_db()
    cursor = conn.cursor()

    # 生成材料编码
    cursor.execute("SELECT MAX(CAST(SUBSTR(material_code, 4) AS INTEGER)) FROM materials WHERE material_code LIKE 'CL-%'")
    max_code = cursor.fetchone()[0] or 0
    material_code = f'CL-{str(max_code + 1).zfill(4)}'

    # 计算不含税价（使用实际税率）
    tax_price = data.get('tax_price', 0)
    tax_rate = data.get('tax_rate', 0.01)
    tax_exempt_price = round(tax_price / (1 + tax_rate), 2) if tax_price else 0

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute("""
        INSERT INTO materials (
            material_code, material_name, specification, unit_id,
            tax_price, tax_exempt_price, freight, remark,
            default_supplier_id, inventory_min, inventory_max, create_time, tax_rate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        material_code, escape(data.get('material_name', '')), escape(data.get('specification', '')),
        data.get('unit_id'), tax_price, tax_exempt_price, data.get('freight', 0),
        escape(data.get('remark', '')), data.get('default_supplier_id'),
        data.get('inventory_min', 0), data.get('inventory_max', 0), now, tax_rate
    ))

    conn.commit()
    material_id = cursor.lastrowid
    conn.close()

    return jsonify({'success': True, 'material_code': material_code, 'id': material_id})


@material_bp.route('/materials/<int:material_id>', methods=['PUT'])
def update_material(material_id):
    """更新材料"""
    data = request.json
    conn = get_db()
    cursor = conn.cursor()

    tax_price = data.get('tax_price', 0)
    tax_rate = data.get('tax_rate', 0.01)
    tax_exempt_price = round(tax_price / (1 + tax_rate), 2) if tax_price else 0

    cursor.execute("""
        UPDATE materials SET
            material_name = ?, specification = ?, unit_id = ?,
            tax_price = ?, tax_exempt_price = ?, freight = ?, remark = ?,
            default_supplier_id = ?, inventory_min = ?, inventory_max = ?, tax_rate = ?
        WHERE id = ?
    """, (
        escape(data.get('material_name', '')), escape(data.get('specification', '')), data.get('unit_id'),
        tax_price, tax_exempt_price, data.get('freight', 0), escape(data.get('remark', '')),
        data.get('default_supplier_id'), data.get('inventory_min', 0),
        data.get('inventory_max', 0), tax_rate, material_id
    ))

    conn.commit()
    conn.close()
    return jsonify({'success': True})


@material_bp.route('/materials/<int:material_id>', methods=['DELETE'])
def delete_material(material_id):
    """删除材料"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM purchase_inquiry_details WHERE material_id = ?", (material_id,))
    if cursor.fetchone()[0] > 0:
        conn.close()
        return jsonify({'success': False, 'message': '该材料已被询价单引用，无法删除'})

    cursor.execute("DELETE FROM materials WHERE id = ?", (material_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})
