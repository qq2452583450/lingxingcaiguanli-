"""
库存蓝图（入库/出库）
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime
from helpers import get_db
from helpers.order_no_generator import generate_stock_in_no, generate_stock_out_no

stock_bp = Blueprint('stock', __name__, url_prefix='/api')


def _pagination_args():
    page = max(request.args.get('page', default=1, type=int) or 1, 1)
    page_size = request.args.get('page_size', default=50, type=int) or 50
    page_size = max(1, min(page_size, 200))
    keyword = (request.args.get('keyword') or '').strip()
    return page, page_size, keyword


# ==================== 入库 ====================

@stock_bp.route('/stock-in', methods=['GET'])
def get_stock_in():
    """分页获取入库明细（每条材料单独一行，含当前库存和出库状态）。"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()

    # 检查用户角色
    cursor.execute("SELECT r.role_name FROM users u LEFT JOIN roles r ON u.role_id = r.id WHERE u.id = ?", (user['id'],))
    role_row = cursor.fetchone()
    role_name = dict(role_row)['role_name'] if role_row else None

    page, page_size, keyword = _pagination_args()
    where = []
    params = []
    if role_name != '系统管理员':
        where.append("si.project_id IN (SELECT project_id FROM user_projects WHERE user_id = ?)")
        params.append(user['id'])
    if keyword:
        like = f'%{keyword}%'
        where.append("""(
            si.order_no LIKE ? OR si.related_order_no LIKE ? OR
            m.material_name LIKE ? OR m.specification LIKE ? OR
            COALESCE(s2.supplier_name, s.supplier_name, '') LIKE ? OR
            COALESCE(p.project_name, '') LIKE ? OR COALESCE(w.warehouse_name, '') LIKE ?
        )""")
        params.extend([like] * 7)
    where_sql = 'WHERE ' + ' AND '.join(where) if where else ''
    from_sql = f"""
        FROM stock_in_details sid
        JOIN stock_in_orders si ON sid.order_id = si.id
        LEFT JOIN materials m ON sid.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        LEFT JOIN suppliers s2 ON sid.supplier_id = s2.id
        LEFT JOIN suppliers s ON si.supplier_id = s.id
        LEFT JOIN projects p ON si.project_id = p.id
        LEFT JOIN warehouses w ON si.warehouse_id = w.id
        LEFT JOIN inventory inv ON sid.material_id = inv.material_id AND inv.warehouse_id = si.warehouse_id
        {where_sql}
    """
    cursor.execute(f"SELECT COUNT(*) {from_sql}", params)
    total = cursor.fetchone()[0]
    offset = (page - 1) * page_size
    cursor.execute(
        f"""
        SELECT
            sid.id, sid.order_id, sid.material_id, si.order_no, si.in_time, si.source_type,
            si.warehouse_id, w.warehouse_name,
            si.status as stock_in_status, si.related_order_no,
            m.material_name, m.specification, u.unit_name,
            sid.quantity, sid.unit_price, sid.amount,
            COALESCE(s2.supplier_name, s.supplier_name) as supplier_name,
            p.project_name,
            COALESCE(inv.quantity, 0) AS current_stock
        {from_sql}
        ORDER BY si.in_time DESC, sid.id ASC
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    )
    details = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({
        'success': True,
        'data': details,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (total + page_size - 1) // page_size),
    })


@stock_bp.route('/stock-in', methods=['POST'])
def create_stock_in():
    """创建入库单"""
    data = request.json
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()

    try:
        order_no = generate_stock_in_no()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        details = data.get('details', [])

        cursor.execute("""
            INSERT INTO stock_in_orders (
                order_no, source_type, related_order_no, supplier_id,
                warehouse_id, operator_id, in_time, status, create_time, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_no, data.get('source_type', '采购入库'), data.get('related_order_no', ''),
            data.get('supplier_id'), data.get('warehouse_id', 1),
            user['id'], now, '已入库', now, data.get('remark', '')
        ))
        order_id = cursor.lastrowid

        for d in details:
            amount = d.get('quantity', 0) * d.get('unit_price', 0)
            cursor.execute("""
                INSERT INTO stock_in_details (order_id, material_id, quantity, unit_price, amount)
                VALUES (?, ?, ?, ?, ?)
            """, (order_id, d.get('material_id'), d.get('quantity', 0),
                  d.get('unit_price', 0), amount))

            # 更新或创建库存（使用REPLACE处理唯一约束）
            cursor.execute("""
                SELECT id FROM inventory WHERE material_id = ? AND warehouse_id = ?
            """, (d.get('material_id'), data.get('warehouse_id', 1)))
            existing = cursor.fetchone()

            if existing:
                cursor.execute("""
                    UPDATE inventory SET quantity = quantity + ?, unit_price = ?, update_time = ?
                    WHERE material_id = ? AND warehouse_id = ?
                """, (d.get('quantity', 0), d.get('unit_price', 0), now,
                      d.get('material_id'), data.get('warehouse_id', 1)))
            else:
                cursor.execute("""
                    INSERT INTO inventory (material_id, warehouse_id, quantity, unit_price, update_time)
                    VALUES (?, ?, ?, ?, ?)
                """, (d.get('material_id'), data.get('warehouse_id', 1),
                      d.get('quantity', 0), d.get('unit_price', 0), now))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'order_no': order_no, 'id': order_id})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': str(e)})


# ==================== 出库 ====================

@stock_bp.route('/stock-out', methods=['GET'])
def get_stock_out():
    """获取所有出库明细（每条材料单独一行）"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()

    # 检查用户角色
    cursor.execute("SELECT r.role_name FROM users u LEFT JOIN roles r ON u.role_id = r.id WHERE u.id = ?", (user['id'],))
    role_row = cursor.fetchone()
    role_name = dict(role_row)['role_name'] if role_row else None

    if role_name == '系统管理员':
        # 管理员可以看到所有
        cursor.execute("""
            SELECT
                sod.id, sod.order_id, so.order_no, so.out_time,
                m.material_name, m.specification, u2.unit_name,
                sod.quantity, sod.unit_price, sod.team_name, sod.receiver_name,
                u.real_name as operator_name, p.project_name, w.warehouse_name
            FROM stock_out_details sod
            JOIN stock_out_orders so ON sod.order_id = so.id
            LEFT JOIN materials m ON sod.material_id = m.id
            LEFT JOIN units u2 ON m.unit_id = u2.id
            LEFT JOIN users u ON so.operator_id = u.id
            LEFT JOIN projects p ON so.project_id = p.id
            LEFT JOIN warehouses w ON so.warehouse_id = w.id
            ORDER BY so.out_time DESC, sod.id ASC
        """)
    else:
        # 材料员只能看到自己绑定项目的出库记录
        cursor.execute("""
            SELECT
                sod.id, sod.order_id, so.order_no, so.out_time,
                m.material_name, m.specification, u2.unit_name,
                sod.quantity, sod.unit_price, sod.team_name, sod.receiver_name,
                u.real_name as operator_name, p.project_name, w.warehouse_name
            FROM stock_out_details sod
            JOIN stock_out_orders so ON sod.order_id = so.id
            LEFT JOIN materials m ON sod.material_id = m.id
            LEFT JOIN units u2 ON m.unit_id = u2.id
            LEFT JOIN users u ON so.operator_id = u.id
            LEFT JOIN projects p ON so.project_id = p.id
            LEFT JOIN warehouses w ON so.warehouse_id = w.id
            WHERE so.project_id IN (SELECT project_id FROM user_projects WHERE user_id = ?)
            ORDER BY so.out_time DESC, sod.id ASC
        """, (user['id'],))

    details = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': details})


@stock_bp.route('/stock-out', methods=['POST'])
def create_stock_out():
    """创建出库单（从入库明细直接出库）"""
    data = request.json
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()

    try:
        order_no = generate_stock_out_no()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        details = data.get('details', [])
        team_name = data.get('team_name', '')
        receiver_name = data.get('receiver_name', '')
        project_id = data.get('project_id')
        warehouse_id = data.get('warehouse_id', 1)

        if not details:
            conn.close()
            return jsonify({'success': False, 'message': '出库明细不能为空'})

        if not team_name and not receiver_name:
            conn.close()
            return jsonify({'success': False, 'message': '请填写领用班组或领用人'})

        cursor.execute("""
            INSERT INTO stock_out_orders (
                order_no, out_type, customer_name, warehouse_id,
                operator_id, out_time, create_time, remark, project_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_no, '领用', '', warehouse_id,
            user['id'], now, now, data.get('remark', ''), project_id
        ))
        order_id = cursor.lastrowid

        for d in details:
            material_id = d.get('material_id')
            quantity = float(d.get('quantity', 0))
            unit_price = float(d.get('unit_price', 0))

            if quantity <= 0:
                raise Exception(f"出库数量必须大于0")

            # 检查库存
            cursor.execute("""
                SELECT quantity FROM inventory WHERE material_id = ? AND warehouse_id = ?
            """, (material_id, warehouse_id))
            inv = cursor.fetchone()
            current_stock = inv['quantity'] if inv else 0

            if current_stock < 1:
                # 查材料名用于友好提示
                cursor.execute("SELECT material_name FROM materials WHERE id = ?", (material_id,))
                mat = cursor.fetchone()
                mat_name = mat['material_name'] if mat else f'ID:{material_id}'
                raise Exception(f"库存不足：「{mat_name}」当前库存为 {current_stock}，无法出库")

            if current_stock < quantity:
                # 查材料名用于友好提示
                cursor.execute("SELECT material_name FROM materials WHERE id = ?", (material_id,))
                mat = cursor.fetchone()
                mat_name = mat['material_name'] if mat else f'ID:{material_id}'
                raise Exception(f"库存不足：「{mat_name}」当前库存仅 {current_stock}，不足出库 {quantity}")

            amount = quantity * unit_price
            cursor.execute("""
                INSERT INTO stock_out_details (order_id, material_id, quantity, unit_price, amount, team_name, receiver_name)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (order_id, material_id, quantity, unit_price, amount,
                  team_name, receiver_name))

            # 扣减库存
            cursor.execute("""
                UPDATE inventory SET quantity = quantity - ?, update_time = ?
                WHERE material_id = ? AND warehouse_id = ?
            """, (quantity, now, material_id, warehouse_id))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'order_no': order_no, 'id': order_id})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': str(e)})


# ==================== 材料出库记录查询 ====================

@stock_bp.route('/stock-out/by-material/<int:material_id>', methods=['GET'])
def get_stock_out_by_material(material_id):
    """查询指定材料的出库历史记录"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            sod.id,
            so.order_no,
            so.out_time,
            sod.quantity,
            sod.unit_price,
            sod.amount,
            sod.team_name,
            sod.receiver_name,
            u.real_name as operator_name,
            w.warehouse_name
        FROM stock_out_details sod
        JOIN stock_out_orders so ON sod.order_id = so.id
        LEFT JOIN users u ON so.operator_id = u.id
        LEFT JOIN warehouses w ON so.warehouse_id = w.id
        WHERE sod.material_id = ?
        ORDER BY so.out_time DESC
    """, (material_id,))
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': records})


# ==================== 库存查询 ====================

@stock_bp.route('/inventory', methods=['GET'])
def get_inventory():
    """分页获取库存。"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()

    # 检查用户角色
    cursor.execute("SELECT r.role_name FROM users u LEFT JOIN roles r ON u.role_id = r.id WHERE u.id = ?", (user['id'],))
    role_row = cursor.fetchone()
    role_name = dict(role_row)['role_name'] if role_row else None

    page, page_size, keyword = _pagination_args()
    permission_sql = ''
    base_params = []
    if role_name != '系统管理员':
        permission_sql = """
            AND (
              m.project_id IN (SELECT project_id FROM user_projects WHERE user_id = ?)
              OR EXISTS (
                 SELECT 1 FROM stock_in_details sid
                 JOIN stock_in_orders sio ON sid.order_id = sio.id
                 WHERE sid.material_id = i.material_id
                   AND sio.project_id IN (SELECT project_id FROM user_projects WHERE user_id = ?)
              )
            )
        """
        base_params.extend([user['id'], user['id']])
    record_filter_sql = ''
    material_id = request.args.get('material_id', type=int)
    warehouse_id = request.args.get('warehouse_id', type=int)
    if material_id:
        record_filter_sql += ' AND i.material_id = ?'
        base_params.append(material_id)
    if warehouse_id:
        record_filter_sql += ' AND i.warehouse_id = ?'
        base_params.append(warehouse_id)
    base_sql = f"""
        SELECT i.*, m.material_name, m.specification, m.material_code,
               COALESCE(
                   NULLIF(m.detail_spec, ''),
                   (SELECT pii.detail_spec
                    FROM purchase_inquiry_items pii
                    WHERE pii.material_id = i.material_id
                      AND pii.detail_spec IS NOT NULL AND pii.detail_spec != ''
                    ORDER BY pii.id DESC LIMIT 1)
               ) AS detail_spec,
               u.unit_name, w.warehouse_name,
               (SELECT p.project_name
                FROM stock_in_details sid
                JOIN stock_in_orders sio ON sid.order_id = sio.id
                JOIN projects p ON sio.project_id = p.id
                WHERE sid.material_id = i.material_id
                ORDER BY sio.in_time DESC LIMIT 1) AS project_name
        FROM inventory i
        LEFT JOIN materials m ON i.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        LEFT JOIN warehouses w ON i.warehouse_id = w.id
        WHERE i.quantity != 0
        {permission_sql}
        {record_filter_sql}
    """
    search_sql = ''
    search_params = []
    if keyword:
        like = f'%{keyword}%'
        search_sql = """
            WHERE material_code LIKE ? OR material_name LIKE ? OR specification LIKE ?
               OR detail_spec LIKE ? OR warehouse_name LIKE ? OR project_name LIKE ?
        """
        search_params = [like] * 6
    cursor.execute(
        f"SELECT COUNT(*) FROM ({base_sql}) inventory_rows {search_sql}",
        [*base_params, *search_params],
    )
    total = cursor.fetchone()[0]
    offset = (page - 1) * page_size
    cursor.execute(
        f"""
        SELECT * FROM ({base_sql}) inventory_rows
        {search_sql}
        ORDER BY material_code
        LIMIT ? OFFSET ?
        """,
        [*base_params, *search_params, page_size, offset],
    )
    inventory = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({
        'success': True,
        'data': inventory,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (total + page_size - 1) // page_size),
    })


@stock_bp.route('/stock-in/<int:stock_in_id>', methods=['DELETE'])
def delete_stock_in(stock_in_id):
    """删除入库明细"""
    user = session.get('user')
    if not user or user.get('role_name') != '系统管理员':
        return jsonify({'success': False, 'message': '仅管理员可删除'})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM stock_in_details WHERE id = ?', (stock_in_id,))
    conn.commit()
    rows = cursor.rowcount
    conn.close()
    return jsonify({'success': rows > 0, 'message': '删除成功' if rows > 0 else '删除失败'})


@stock_bp.route('/stock-out/<int:stock_out_id>', methods=['DELETE'])
def delete_stock_out(stock_out_id):
    """删除出库明细"""
    user = session.get('user')
    if not user or user.get('role_name') != '系统管理员':
        return jsonify({'success': False, 'message': '仅管理员可删除'})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM stock_out_details WHERE id = ?', (stock_out_id,))
    conn.commit()
    rows = cursor.rowcount
    conn.close()
    return jsonify({'success': rows > 0, 'message': '删除成功' if rows > 0 else '删除失败'})


@stock_bp.route('/inventory/<int:material_id>', methods=['DELETE'])
def delete_inventory(material_id):
    """删除库存记录（需指定仓库）"""
    user = session.get('user')
    if not user or user.get('role_name') != '系统管理员':
        return jsonify({'success': False, 'message': '仅管理员可删除'})
    warehouse_id = request.args.get('warehouse_id', type=int)
    if not warehouse_id:
        return jsonify({'success': False, 'message': '缺少仓库ID'})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM inventory WHERE material_id = ? AND warehouse_id = ?', (material_id, warehouse_id))
    conn.commit()
    rows = cursor.rowcount
    conn.close()
    return jsonify({'success': rows > 0, 'message': '删除成功' if rows > 0 else '删除失败'})
