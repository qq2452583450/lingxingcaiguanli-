"""
材料管理蓝图
"""
from io import BytesIO

from flask import Blueprint, request, jsonify, send_file, session
from datetime import datetime
from helpers import get_db
from helpers.auth_decorators import login_required, require_role, require_admin
from helpers.material_regions import generate_material_code, get_region_name

material_bp = Blueprint('materials', __name__, url_prefix='/api')


def _material_filter_clause():
    """Build the shared material-list filters for the page and Excel export."""
    keyword = request.args.get('keyword', '')
    filter_name = request.args.get('filter_name', '')
    filter_spec = request.args.get('filter_spec', '')
    filter_brand = request.args.get('filter_brand', '')
    filter_region = request.args.get('filter_region', '')

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
    return where_clause, params


def _material_export_workbook(rows, filters):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    info = workbook.active
    info.title = '导出说明'
    info.append(['材料信息导出'])
    info.append(['导出时间', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    info.append(['材料数量', len(rows)])
    for label, key in [('材料名称', 'filter_name'), ('规格', 'filter_spec'), ('品牌', 'filter_brand'), ('地区', 'filter_region')]:
        info.append([label, filters.get(key) or '全部'])

    sheet = workbook.create_sheet('材料信息')
    headers = [
        '材料编号', '地区', '项目', '材料名称', '规格', '详细规格', '品牌', '单位', '是否国标',
        '税率', '含税价', '不含税价', '现金含税价', '现金不含税价', '默认供应商', '运费',
        '库存下限', '库存上限', '重量', '最后采购项目', '最后采购时间', '创建时间', '备注',
    ]
    sheet.append(headers)
    for row in rows:
        sheet.append([
            row.get('material_code') or '',
            get_region_name(row.get('material_code')) or '',
            row.get('project_name') or '',
            row.get('material_name') or '',
            row.get('specification') or '',
            row.get('detail_spec') or '',
            row.get('brand') or '',
            row.get('unit_name') or '',
            '是' if row.get('is_national_standard') else '否',
            row.get('tax_rate') or 0,
            row.get('tax_price') or 0,
            row.get('tax_exempt_price') or 0,
            row.get('cash_price') or 0,
            row.get('cash_tax_price') or 0,
            row.get('supplier_name') or '',
            row.get('freight') or 0,
            row.get('inventory_min') or 0,
            row.get('inventory_max') or 0,
            row.get('weight') or 0,
            row.get('last_purchase_project') or '',
            row.get('last_purchase_time') or '',
            row.get('create_time') or '',
            row.get('remark') or '',
        ])

    title_fill = PatternFill('solid', fgColor='1F4E78')
    for sheet_item in (info, sheet):
        sheet_item.sheet_view.showGridLines = False
        sheet_item.freeze_panes = 'A2'
        for cell in sheet_item[1]:
            cell.font = Font(color='FFFFFF', bold=True)
            cell.fill = title_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
    info.column_dimensions['A'].width = 18
    info.column_dimensions['B'].width = 30
    sheet.auto_filter.ref = sheet.dimensions
    widths = [16, 10, 22, 24, 22, 26, 16, 10, 12, 10, 13, 13, 15, 15, 26, 12, 12, 12, 10, 22, 20, 20, 34]
    for column, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(column)].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = 's'
            cell.alignment = Alignment(vertical='center', wrap_text=True)
    for column in (11, 12, 13, 14, 16, 17, 18, 19):
        for row in sheet.iter_rows(min_row=2, min_col=column, max_col=column):
            row[0].number_format = '#,##0.00'
    for row in sheet.iter_rows(min_row=2, min_col=10, max_col=10):
        row[0].number_format = '0.00%'

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


@material_bp.route('/materials', methods=['GET'])
def get_materials():
    """获取材料列表（支持分页和筛选）"""
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    offset = (page - 1) * page_size

    conn = get_db()
    cursor = conn.cursor()

    where_clause, params = _material_filter_clause()

    # 查询总数
    count_sql = f'SELECT COUNT(*) FROM materials m {where_clause}'
    cursor.execute(count_sql, params)
    total = cursor.fetchone()[0]

    # 查询分页数据
    sql = f"""
        WITH ranked_purchases AS (
            SELECT
                pii.material_id,
                pi.project_id,
                COALESCE(
                    NULLIF(pi.approve_time, ''),
                    NULLIF(pi.inquiry_date, ''),
                    pi.create_time
                ) AS purchase_time,
                ROW_NUMBER() OVER (
                    PARTITION BY pii.material_id
                    ORDER BY
                        COALESCE(
                            NULLIF(pi.approve_time, ''),
                            NULLIF(pi.inquiry_date, ''),
                            pi.create_time
                        ) DESC,
                        pi.id DESC,
                        pii.id DESC
                ) AS purchase_rank
            FROM purchase_inquiry_items pii
            JOIN purchase_inquiries pi ON pi.id = pii.inquiry_id
            WHERE pi.approval_status = '已同意'
        )
        SELECT
            m.*,
            u.unit_name,
            s.supplier_name,
            COALESCE(lp.project_name, lp.project_code, '') AS last_purchase_project,
            rp.purchase_time AS last_purchase_time
        FROM materials m
        LEFT JOIN units u ON m.unit_id = u.id
        LEFT JOIN suppliers s ON m.default_supplier_id = s.id
        LEFT JOIN ranked_purchases rp
            ON rp.material_id = m.id AND rp.purchase_rank = 1
        LEFT JOIN projects lp ON lp.id = rp.project_id
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


@material_bp.route('/materials/<int:material_id>/price-history', methods=['GET'])
def get_material_price_history(material_id):
    """获取材料审批通过后的采购价格历史。"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT m.id, m.material_code, m.material_name, m.specification, m.detail_spec, m.brand, u.unit_name
        FROM materials m
        LEFT JOIN units u ON u.id = m.unit_id
        WHERE m.id = ?
    """, (material_id,))
    material_row = cursor.fetchone()
    if not material_row:
        conn.close()
        return jsonify({'success': False, 'message': '材料不存在'}), 404

    cursor.execute("""
        WITH ranked_quotes AS (
            SELECT
                pii.id AS item_id,
                pii.is_cash_price,
                pii.quantity,
                pi.id AS inquiry_id,
                pi.inquiry_no,
                pi.project_id,
                COALESCE(NULLIF(pi.approve_time, ''), NULLIF(pi.inquiry_date, ''), pi.create_time) AS purchase_time,
                q.tax_price,
                q.tax_rate,
                q.supplier_id,
                ROW_NUMBER() OVER (
                    PARTITION BY pii.id
                    ORDER BY q.is_selected DESC, q.is_lowest DESC, q.id ASC
                ) AS quote_rank
            FROM purchase_inquiry_items pii
            JOIN purchase_inquiries pi ON pi.id = pii.inquiry_id
            JOIN purchase_inquiry_quotes q ON q.item_id = pii.id
            WHERE pii.material_id = ?
              AND pi.approval_status = '已同意'
              AND q.tax_price > 0
              AND (q.is_selected = 1 OR q.is_lowest = 1)
        )
        SELECT
            rq.inquiry_id,
            rq.inquiry_no,
            rq.purchase_time,
            rq.quantity,
            rq.tax_price,
            rq.tax_rate,
            rq.is_cash_price,
            COALESCE(p.project_name, p.project_code, '') AS project_name,
            COALESCE(s.supplier_name, '') AS supplier_name
        FROM ranked_quotes rq
        LEFT JOIN projects p ON p.id = rq.project_id
        LEFT JOIN suppliers s ON s.id = rq.supplier_id
        WHERE rq.quote_rank = 1
        ORDER BY rq.purchase_time DESC, rq.inquiry_id DESC, rq.item_id DESC
    """, (material_id,))
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        'success': True,
        'material': dict(material_row),
        'data': history,
    })


@material_bp.route('/materials/export', methods=['GET'])
@login_required
def export_materials():
    """Export every material matching the current material-list filters."""
    where_clause, params = _material_filter_clause()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"""
        WITH ranked_purchases AS (
            SELECT
                pii.material_id,
                pi.project_id,
                COALESCE(
                    NULLIF(pi.approve_time, ''),
                    NULLIF(pi.inquiry_date, ''),
                    pi.create_time
                ) AS purchase_time,
                ROW_NUMBER() OVER (
                    PARTITION BY pii.material_id
                    ORDER BY
                        COALESCE(
                            NULLIF(pi.approve_time, ''),
                            NULLIF(pi.inquiry_date, ''),
                            pi.create_time
                        ) DESC,
                        pi.id DESC,
                        pii.id DESC
                ) AS purchase_rank
            FROM purchase_inquiry_items pii
            JOIN purchase_inquiries pi ON pi.id = pii.inquiry_id
            WHERE pi.approval_status = '已同意'
        )
        SELECT
            m.*,
            u.unit_name,
            s.supplier_name,
            COALESCE(mp.project_name, mp.project_code, '') AS project_name,
            COALESCE(lp.project_name, lp.project_code, '') AS last_purchase_project,
            rp.purchase_time AS last_purchase_time
        FROM materials m
        LEFT JOIN units u ON m.unit_id = u.id
        LEFT JOIN suppliers s ON m.default_supplier_id = s.id
        LEFT JOIN projects mp ON mp.id = m.project_id
        LEFT JOIN ranked_purchases rp
            ON rp.material_id = m.id AND rp.purchase_rank = 1
        LEFT JOIN projects lp ON lp.id = rp.project_id
        {where_clause}
        ORDER BY m.material_code
    """, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    output = _material_export_workbook(rows, request.args)
    return send_file(
        output,
        as_attachment=True,
        download_name='材料信息导出.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


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

    material_code = generate_material_code(cursor, proj_row[0], session.get('user'))
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
    material_code = generate_material_code(cursor, proj_row[0], session.get('user'))

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
        material_code = generate_material_code(cursor, proj_row[0], session.get('user'))

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
