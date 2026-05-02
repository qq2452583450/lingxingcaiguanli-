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


@material_bp.route('/next-material-code', methods=['GET'])
def get_next_material_code():
    """获取下一个材料编码"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    project_id = request.args.get('project_id', type=int)
    if not project_id:
        return jsonify({'success': False, 'message': '缺少项目ID'})

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT project_code FROM projects WHERE id = ?', (project_id,))
    proj_row = cursor.fetchone()
    if not proj_row:
        conn.close()
        return jsonify({'success': False, 'message': '项目不存在'})

    project_code = proj_row[0]
    prefix = project_code[:2].upper() + 'LX'

    cursor.execute("SELECT material_code FROM materials WHERE material_code LIKE ? ORDER BY id DESC LIMIT 1",
                   (prefix + '%',))
    last_row = cursor.fetchone()

    if last_row:
        last_code = last_row[0]
        try:
            num = int(last_code[len(prefix):])
            next_num = num + 1
        except ValueError:
            next_num = 1
    else:
        next_num = 1

    material_code = prefix + str(next_num).zfill(5)
    conn.close()

    return jsonify({'success': True, 'material_code': material_code})


@material_bp.route('/materials', methods=['POST'])
def create_material():
    """创建材料"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})
    if user.get('role_name') not in ('系统管理员', '材料员'):
        return jsonify({'success': False, 'message': '仅管理员或材料员可添加材料'})

    data = request.json
    conn = get_db()
    cursor = conn.cursor()

    project_id = data.get('project_id')
    if not project_id:
        conn.close()
        return jsonify({'success': False, 'message': '缺少项目ID'})

    cursor.execute('SELECT project_code FROM projects WHERE id = ?', (project_id,))
    proj_row = cursor.fetchone()
    if not proj_row:
        conn.close()
        return jsonify({'success': False, 'message': '项目不存在'})
    project_code = proj_row[0]

    prefix = project_code[:2].upper() + 'LX'

    cursor.execute("SELECT material_code FROM materials WHERE material_code LIKE ? ORDER BY id DESC LIMIT 1",
                   (prefix + '%',))
    last_row = cursor.fetchone()
    if last_row:
        last_code = last_row[0]
        try:
            num = int(last_code[len(prefix):])
            next_num = num + 1
        except ValueError:
            next_num = 1
    else:
        next_num = 1
    material_code = prefix + str(next_num).zfill(5)

    tax_price = data.get('tax_price', 0)
    tax_rate = data.get('tax_rate', 0.01)
    tax_exempt_price = round(tax_price / (1 + tax_rate), 2) if tax_price else 0

    unit_name = data.get('unit_name', '')
    if unit_name:
        cursor.execute('SELECT id FROM units WHERE unit_name = ?', (unit_name,))
        row = cursor.fetchone()
        if row:
            unit_id = row[0]
        else:
            cursor.execute('INSERT INTO units (unit_name) VALUES (?)', (unit_name,))
            unit_id = cursor.lastrowid
    else:
        unit_id = None

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute("""
        INSERT INTO materials (
            material_code, material_name, specification, detail_spec, is_national_standard, brand,
            unit_id, tax_price, tax_exempt_price, freight, remark,
            default_supplier_id, inventory_min, inventory_max, create_time, tax_rate, project_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        material_code, escape(data.get('material_name', '')), escape(data.get('specification', '')),
        escape(data.get('detail_spec', '')), data.get('is_national_standard', 0), escape(data.get('brand', '')),
        unit_id, tax_price, tax_exempt_price, data.get('freight', 0),
        escape(data.get('remark', '')), data.get('default_supplier_id'),
        data.get('inventory_min', 0), data.get('inventory_max', 0), now, tax_rate, project_id
    ))

    conn.commit()
    material_id = cursor.lastrowid
    conn.close()

    return jsonify({'success': True, 'material_code': material_code, 'id': material_id})


@material_bp.route('/materials/<int:material_id>', methods=['PUT'])
def update_material(material_id):
    """更新材料"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})
    if user.get('role_name') not in ('系统管理员', '材料员'):
        return jsonify({'success': False, 'message': '仅管理员或材料员可修改材料'})
    data = request.json
    conn = get_db()
    cursor = conn.cursor()

    # 判断是材料员还是管理员
    is_admin = user.get('role_name') == '系统管理员'

    # 税务计算
    tax_price = data.get('tax_price', 0)
    tax_rate = data.get('tax_rate', 0.01)
    tax_exempt_price = round(tax_price / (1 + tax_rate), 2) if tax_price else 0

    # 处理单位（可能是名称或ID）
    unit_name = data.get('unit_name', '')
    if unit_name:
        cursor.execute('SELECT id FROM units WHERE unit_name = ?', (unit_name,))
        row = cursor.fetchone()
        if row:
            unit_id = row[0]
        else:
            cursor.execute('INSERT INTO units (unit_name) VALUES (?)', (unit_name,))
            unit_id = cursor.lastrowid
    else:
        unit_id = None

    if is_admin:
        # 管理员可以更新所有字段，包括价格和供应商
        cursor.execute("""
            UPDATE materials SET
                material_name = ?, specification = ?, detail_spec = ?, is_national_standard = ?, brand = ?,
                unit_id = ?, tax_price = ?, tax_exempt_price = ?, freight = ?, remark = ?,
                default_supplier_id = ?, inventory_min = ?, inventory_max = ?, tax_rate = ?
            WHERE id = ?
        """, (
            escape(data.get('material_name', '')), escape(data.get('specification', '')),
            escape(data.get('detail_spec', '')), data.get('is_national_standard', 0), escape(data.get('brand', '')),
            unit_id, tax_price, tax_exempt_price, data.get('freight', 0), escape(data.get('remark', '')),
            data.get('default_supplier_id'), data.get('inventory_min', 0),
            data.get('inventory_max', 0), tax_rate, material_id
        ))
    else:
        # 材料员只能更新基础信息，不能修改价格和供应商
        cursor.execute("""
            UPDATE materials SET
                material_name = ?, specification = ?, detail_spec = ?, is_national_standard = ?, brand = ?,
                unit_id = ?, freight = ?, remark = ?, inventory_min = ?, inventory_max = ?, tax_rate = ?
            WHERE id = ?
        """, (
            escape(data.get('material_name', '')), escape(data.get('specification', '')),
            escape(data.get('detail_spec', '')), data.get('is_national_standard', 0), escape(data.get('brand', '')),
            unit_id, data.get('freight', 0), escape(data.get('remark', '')),
            data.get('inventory_min', 0), data.get('inventory_max', 0), tax_rate, material_id
        ))

    conn.commit()
    conn.close()
    return jsonify({'success': True})


@material_bp.route('/materials/<int:material_id>', methods=['DELETE'])
def delete_material(material_id):
    """删除材料"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})
    if user.get('role_name') != '系统管理员':
        return jsonify({'success': False, 'message': '仅管理员可修改材料信息'})
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
