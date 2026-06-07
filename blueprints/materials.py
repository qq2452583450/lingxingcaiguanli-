"""
材料管理蓝图
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime
from helpers import get_db
from helpers.auth_decorators import login_required, require_role, require_admin

material_bp = Blueprint('materials', __name__, url_prefix='/api')


@material_bp.route('/materials', methods=['GET'])
def get_materials():
    """获取材料列表（支持分页和筛选）"""
    keyword = request.args.get('keyword', '')
    filter_name = request.args.get('filter_name', '')
    filter_spec = request.args.get('filter_spec', '')
    filter_brand = request.args.get('filter_brand', '')
    filter_region = request.args.get('filter_region', '')
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    offset = (page - 1) * page_size

    conn = get_db()
    cursor = conn.cursor()

    # 构建 WHERE 条件
    where_clause = ''
    params = []
    if filter_name:
        where_clause += ' AND m.material_name LIKE ?'
        params.append(f'%{filter_name}%')
    if filter_spec:
        where_clause += ' AND m.specification LIKE ?'
        params.append(f'%{filter_spec}%')
    if filter_brand:
        where_clause += ' AND m.brand LIKE ?'
        params.append(f'%{filter_brand}%')
    if filter_region:
        where_clause += ' AND UPPER(SUBSTR(m.material_code, 1, 2)) = ?'
        params.append(filter_region.upper())
    if keyword:
        like = f'%{keyword}%'
        where_clause += ' AND (m.material_name LIKE ? OR m.material_code LIKE ? OR m.specification LIKE ? OR m.detail_spec LIKE ? OR m.brand LIKE ?)'
        params.extend([like, like, like, like, like])
    if where_clause:
        where_clause = 'WHERE ' + where_clause[4:]

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
@login_required
def get_next_material_code():
    """获取下一个材料编码"""
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

    cursor.execute("SELECT material_code FROM materials WHERE material_code LIKE ? ORDER BY material_code DESC LIMIT 1",
                   (prefix + '%',))
    last_row = cursor.fetchone()

    if last_row:
        last_code = last_row[0]
        try:
            next_num = int(last_code[len(prefix):]) + 1
        except ValueError:
            next_num = 1
    else:
        next_num = 1

    material_code = prefix + str(next_num).zfill(5)
    while True:
        cursor.execute("SELECT 1 FROM materials WHERE material_code = ?", (material_code,))
        if not cursor.fetchone():
            break
        next_num += 1
        material_code = prefix + str(next_num).zfill(5)
    conn.close()

    return jsonify({'success': True, 'material_code': material_code})


@material_bp.route('/materials', methods=['POST'])
@require_role('系统管理员', '材料员')
def create_material():
    """创建材料"""
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

    cursor.execute("SELECT material_code FROM materials WHERE material_code LIKE ? ORDER BY material_code DESC LIMIT 1",
                   (prefix + '%',))
    last_row = cursor.fetchone()
    if last_row:
        last_code = last_row[0]
        try:
            next_num = int(last_code[len(prefix):]) + 1
        except ValueError:
            next_num = 1
    else:
        next_num = 1
    material_code = prefix + str(next_num).zfill(5)
    while True:
        cursor.execute("SELECT 1 FROM materials WHERE material_code = ?", (material_code,))
        if not cursor.fetchone():
            break
        next_num += 1
        material_code = prefix + str(next_num).zfill(5)

    tax_price = data.get('tax_price', 0)
    tax_rate = data.get('tax_rate', 0.01)
    tax_exempt_price = round(tax_price / (1 + tax_rate), 2) if tax_price else 0

    # 现金含税价处理
    is_cash_price = data.get('is_cash_price', 0)
    cash_price = data.get('cash_price', 0)  # 用户输入的现金含税价
    cash_tax_price = round(cash_price / (1 + tax_rate), 2) if cash_price and tax_rate else 0

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
            unit_id, tax_price, tax_exempt_price, is_cash_price, cash_price, cash_tax_price, freight, remark,
            default_supplier_id, inventory_min, inventory_max, create_time, tax_rate, project_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        material_code, data.get('material_name', ''), data.get('specification', ''),
        data.get('detail_spec', ''), data.get('is_national_standard', 0), data.get('brand', ''),
        unit_id, tax_price, tax_exempt_price, is_cash_price, cash_price, cash_tax_price, data.get('freight', 0),
        data.get('remark', ''), data.get('default_supplier_id'),
        data.get('inventory_min', 0), data.get('inventory_max', 0), now, tax_rate, project_id
    ))

    conn.commit()
    material_id = cursor.lastrowid
    conn.close()

    return jsonify({'success': True, 'material_code': material_code, 'id': material_id})


@material_bp.route('/materials/batch', methods=['POST'])
def create_materials_batch():
    """批量创建材料"""
    data = request.get_json()
    items = data.get('items', [])
    region = data.get('region', '')
    if not items:
        return jsonify({'success': False, 'message': '请至少添加一条材料'})

    conn = get_db()
    cursor = conn.cursor()
    created = 0

    for item in items:
        project_id = item.get('project_id')
        if not project_id:
            continue

        cursor.execute('SELECT project_code FROM projects WHERE id = ?', (project_id,))
        proj_row = cursor.fetchone()
        if not proj_row:
            continue
        project_code = proj_row[0]
        prefix = project_code[:2].upper() + 'LX'

        # 生成不重复编号
        cursor.execute("SELECT material_code FROM materials WHERE material_code LIKE ? ORDER BY material_code DESC LIMIT 1", (prefix + '%',))
        last_row = cursor.fetchone()
        if last_row:
            try:
                next_num = int(last_row[0][len(prefix):]) + 1
            except ValueError:
                next_num = 1
        else:
            next_num = 1
        material_code = prefix + str(next_num).zfill(5)
        while True:
            cursor.execute("SELECT 1 FROM materials WHERE material_code = ?", (material_code,))
            if not cursor.fetchone():
                break
            next_num += 1
            material_code = prefix + str(next_num).zfill(5)

        tax_price = item.get('tax_price', 0)
        tax_rate = item.get('tax_rate', 0.01)
        tax_exempt_price = round(tax_price / (1 + tax_rate), 2) if tax_price else 0

        cash_price = item.get('cash_price', 0)
        is_cash_price = 1 if cash_price > 0 else 0
        cash_tax_price = round(cash_price / (1 + tax_rate), 2) if cash_price and tax_rate else 0

        unit_name = item.get('unit_name', '')
        unit_id = None
        if unit_name:
            cursor.execute('SELECT id FROM units WHERE unit_name = ?', (unit_name,))
            row = cursor.fetchone()
            if row:
                unit_id = row[0]
            else:
                cursor.execute('INSERT INTO units (unit_name) VALUES (?)', (unit_name,))
                unit_id = cursor.lastrowid

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT INTO materials (
                material_code, material_name, specification, detail_spec, is_national_standard, brand,
                unit_id, tax_price, tax_exempt_price, is_cash_price, cash_price, cash_tax_price, freight, remark,
                default_supplier_id, inventory_min, inventory_max, create_time, tax_rate, project_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            material_code, item.get('material_name', ''), item.get('specification', ''),
            item.get('detail_spec', ''), item.get('is_national_standard', 0), item.get('brand', ''),
            unit_id, tax_price, tax_exempt_price, is_cash_price, cash_price, cash_tax_price, item.get('freight', 0),
            item.get('remark', ''), item.get('default_supplier_id'),
            item.get('inventory_min', 0), item.get('inventory_max', 0), now, tax_rate, project_id
        ))
        created += 1

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'created': created})


@material_bp.route('/materials/<int:material_id>', methods=['PUT'])
@require_role('系统管理员', '材料员')
def update_material(material_id):
    """更新材料"""
    data = request.json
    conn = get_db()
    cursor = conn.cursor()

    # 判断是材料员还是管理员
    is_admin = session.get('user', {}).get('role_name') == '系统管理员'

    # 税务计算
    tax_price = data.get('tax_price', 0)
    tax_rate = data.get('tax_rate', 0.01)
    tax_exempt_price = round(tax_price / (1 + tax_rate), 2) if tax_price else 0

    # 现金含税价处理
    is_cash_price = data.get('is_cash_price', 0)
    cash_price = data.get('cash_price', 0)  # 用户输入的现金含税价
    cash_tax_price = round(cash_price / (1 + tax_rate), 2) if cash_price and tax_rate else 0

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
                unit_id = ?, tax_price = ?, tax_exempt_price = ?, is_cash_price = ?, cash_price = ?, cash_tax_price = ?,
                freight = ?, remark = ?,
                default_supplier_id = ?, inventory_min = ?, inventory_max = ?, tax_rate = ?
            WHERE id = ?
        """, (
            data.get('material_name', ''), data.get('specification', ''),
            data.get('detail_spec', ''), data.get('is_national_standard', 0), data.get('brand', ''),
            unit_id, tax_price, tax_exempt_price, is_cash_price, cash_price, cash_tax_price,
            data.get('freight', 0), data.get('remark', ''),
            data.get('default_supplier_id'), data.get('inventory_min', 0),
            data.get('inventory_max', 0), tax_rate, material_id
        ))
    else:
        # 材料员可以更新基础信息和价格，但不能修改供应商
        cursor.execute("""
            UPDATE materials SET
                material_name = ?, specification = ?, detail_spec = ?, is_national_standard = ?, brand = ?,
                unit_id = ?, tax_price = ?, tax_exempt_price = ?, is_cash_price = ?, cash_price = ?, cash_tax_price = ?,
                freight = ?, remark = ?, inventory_min = ?, inventory_max = ?, tax_rate = ?
            WHERE id = ?
        """, (
            data.get('material_name', ''), data.get('specification', ''),
            data.get('detail_spec', ''), data.get('is_national_standard', 0), data.get('brand', ''),
            unit_id, tax_price, tax_exempt_price, is_cash_price, cash_price, cash_tax_price,
            data.get('freight', 0), data.get('remark', ''),
            data.get('inventory_min', 0), data.get('inventory_max', 0), tax_rate, material_id
        ))

    conn.commit()
    conn.close()
    return jsonify({'success': True})


@material_bp.route('/materials/<int:material_id>', methods=['DELETE'])
@require_admin
def delete_material(material_id):
    """删除材料"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM purchase_inquiry_details WHERE material_id = ?", (material_id,))
    if cursor.fetchone()[0] > 0:
        conn.close()
        return jsonify({'success': False, 'message': '该材料已被询价单引用，无法删除'})

    cursor.execute("SELECT COUNT(*) FROM purchase_inquiry_items WHERE material_id = ?", (material_id,))
    if cursor.fetchone()[0] > 0:
        conn.close()
        return jsonify({'success': False, 'message': '该材料已被询价单引用，无法删除'})

    # 删除关联的库存记录（库存为0时允许级联删除）
    cursor.execute("DELETE FROM inventory WHERE material_id = ?", (material_id,))

    cursor.execute("DELETE FROM materials WHERE id = ?", (material_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})
