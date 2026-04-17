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
    """获取所有入库单"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT si.*, s.supplier_name, w.warehouse_name, u.real_name as operator_name
        FROM stock_in_orders si
        LEFT JOIN suppliers s ON si.supplier_id = s.id
        LEFT JOIN warehouses w ON si.warehouse_id = w.id
        LEFT JOIN users u ON si.operator_id = u.id
        ORDER BY si.create_time DESC
    """)
    stock_in = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': stock_in})


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
    """获取所有出库单"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT so.*, w.warehouse_name, u.real_name as operator_name
        FROM stock_out_orders so
        LEFT JOIN warehouses w ON so.warehouse_id = w.id
        LEFT JOIN users u ON so.operator_id = u.id
        ORDER BY so.create_time DESC
    """)
    stock_out = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': stock_out})


@stock_bp.route('/stock-out', methods=['POST'])
def create_stock_out():
    """创建出库单"""
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

        cursor.execute("""
            INSERT INTO stock_out_orders (
                order_no, out_type, customer_name, warehouse_id,
                operator_id, out_time, create_time, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_no, escape(data.get('out_type', '领用')), escape(data.get('customer_name', '')),
            data.get('warehouse_id', 1), user['id'], now, now, escape(data.get('remark', ''))
        ))
        order_id = cursor.lastrowid

        for d in details:
            amount = d.get('quantity', 0) * d.get('unit_price', 0)
            cursor.execute("""
                INSERT INTO stock_out_details (order_id, material_id, quantity, unit_price, amount)
                VALUES (?, ?, ?, ?, ?)
            """, (order_id, d.get('material_id'), d.get('quantity', 0),
                  d.get('unit_price', 0), amount))

            # 扣减库存（防止负数）
            cursor.execute("""
                UPDATE inventory SET quantity = quantity - ?, update_time = ?
                WHERE material_id = ? AND warehouse_id = ? AND quantity >= ?
            """, (d.get('quantity', 0), now, d.get('material_id'), data.get('warehouse_id', 1), d.get('quantity', 0)))
            if cursor.rowcount == 0:
                # 库存不足，回滚
                raise Exception(f"库存不足：材料ID {d.get('material_id')} 在仓库 {data.get('warehouse_id', 1)} 库存不足")

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'order_no': order_no, 'id': order_id})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': str(e)})


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
