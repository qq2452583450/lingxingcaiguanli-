"""
库存蓝图（入库/出库）
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime
from html import escape
from helpers import get_db

stock_bp = Blueprint('stock', __name__, url_prefix='/api')


def generate_stock_in_no():
    """生成入库单号"""
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y%m%d')
    cursor.execute("SELECT COUNT(*) FROM stock_in_orders WHERE order_no LIKE ?", (f'JH-{today}%',))
    count = cursor.fetchone()[0] + 1
    conn.close()
    return f'JH-{today}-{str(count).zfill(3)}'


def generate_stock_out_no():
    """生成出库单号"""
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y%m%d')
    cursor.execute("SELECT COUNT(*) FROM stock_out_orders WHERE order_no LIKE ?", (f'CK-{today}%',))
    count = cursor.fetchone()[0] + 1
    conn.close()
    return f'CK-{today}-{str(count).zfill(3)}'


# ==================== 入库 ====================

@stock_bp.route('/stock-in', methods=['GET'])
def get_stock_in():
    """获取所有入库明细（每条材料单独一行，含当前库存和出库状态）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            sid.id,
            sid.order_id,
            sid.material_id,
            si.order_no,
            si.in_time,
            si.source_type,
            m.material_name,
            m.specification,
            u.unit_name,
            sid.quantity,
            sid.unit_price,
            sid.amount,
            s.supplier_name,
            p.project_name,
            COALESCE(inv.quantity, 0) AS current_stock
        FROM stock_in_details sid
        JOIN stock_in_orders si ON sid.order_id = si.id
        LEFT JOIN materials m ON sid.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        LEFT JOIN suppliers s ON si.supplier_id = s.id
        LEFT JOIN projects p ON si.project_id = p.id
        LEFT JOIN inventory inv ON sid.material_id = inv.material_id AND inv.warehouse_id = 1
        ORDER BY si.in_time DESC, sid.id ASC
    """)
    details = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': details})


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
            order_no, escape(data.get('source_type', '采购入库')), escape(data.get('related_order_no', '')),
            data.get('supplier_id'), data.get('warehouse_id', 1),
            user['id'], now, '已入库', now, escape(data.get('remark', ''))
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
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            sod.id,
            sod.order_id,
            so.order_no,
            so.out_time,
            m.material_name,
            m.specification,
            u2.unit_name,
            sod.quantity,
            sod.unit_price,
            sod.team_name,
            sod.receiver_name,
            u.real_name as operator_name
        FROM stock_out_details sod
        JOIN stock_out_orders so ON sod.order_id = so.id
        LEFT JOIN materials m ON sod.material_id = m.id
        LEFT JOIN units u2 ON m.unit_id = u2.id
        LEFT JOIN users u ON so.operator_id = u.id
        ORDER BY so.out_time DESC, sod.id ASC
    """)
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
            order_no, '领用', '', 1,
            user['id'], now, now, escape(data.get('remark', '')), project_id
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
            """, (material_id, 1))
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
                  escape(team_name), escape(receiver_name)))

            # 扣减库存
            cursor.execute("""
                UPDATE inventory SET quantity = quantity - ?, update_time = ?
                WHERE material_id = ? AND warehouse_id = ?
            """, (quantity, now, material_id, 1))

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
            u.real_name as operator_name
        FROM stock_out_details sod
        JOIN stock_out_orders so ON sod.order_id = so.id
        LEFT JOIN users u ON so.operator_id = u.id
        WHERE sod.material_id = ?
        ORDER BY so.out_time DESC
    """, (material_id,))
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': records})


# ==================== 库存查询 ====================

@stock_bp.route('/inventory', methods=['GET'])
def get_inventory():
    """获取库存"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.*, m.material_name, m.specification, m.material_code,
               u.unit_name, w.warehouse_name
        FROM inventory i
        LEFT JOIN materials m ON i.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        LEFT JOIN warehouses w ON i.warehouse_id = w.id
        ORDER BY m.material_code
    """)
    inventory = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': inventory})


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
    """删除库存记录"""
    user = session.get('user')
    if not user or user.get('role_name') != '系统管理员':
        return jsonify({'success': False, 'message': '仅管理员可删除'})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM inventory WHERE material_id = ?', (material_id,))
    conn.commit()
    rows = cursor.rowcount
    conn.close()
    return jsonify({'success': rows > 0, 'message': '删除成功' if rows > 0 else '删除失败'})
