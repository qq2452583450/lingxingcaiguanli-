"""
仪表盘蓝图
"""
from flask import Blueprint, jsonify
import sqlite3
import config
from datetime import datetime

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api')


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@dashboard_bp.route('/dashboard', methods=['GET'])
def get_dashboard():
    """获取仪表盘数据"""
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')

    # 待审批数量
    cursor.execute("""
        SELECT COUNT(*) FROM purchase_inquiries
        WHERE approval_status = '待审批' OR approval_status = '材料员已审'
    """)
    pending = cursor.fetchone()[0]

    # 库存预警数量
    cursor.execute("""
        SELECT COUNT(*) FROM materials m
        LEFT JOIN inventory i ON m.id = i.material_id
        WHERE m.inventory_min > 0 AND (i.quantity IS NULL OR i.quantity < m.inventory_min)
    """)
    warning = cursor.fetchone()[0]

    # 今日入库数量
    cursor.execute("SELECT COUNT(*) FROM stock_in_orders WHERE DATE(in_time) = ?", (today,))
    today_in = cursor.fetchone()[0]

    # 今日销售数量
    cursor.execute("SELECT COUNT(*) FROM sales_orders WHERE DATE(create_time) = ?", (today,))
    today_out = cursor.fetchone()[0]

    # 总材料数
    cursor.execute("SELECT COUNT(*) FROM materials")
    total_materials = cursor.fetchone()[0]

    # 总供应商数
    cursor.execute("SELECT COUNT(*) FROM suppliers")
    total_suppliers = cursor.fetchone()[0]

    # 总客户数
    cursor.execute("SELECT COUNT(*) FROM customers")
    total_customers = cursor.fetchone()[0]

    conn.close()

    return jsonify({
        'success': True,
        'data': {
            'pending': pending,
            'warning': warning,
            'today_in': today_in,
            'today_out': today_out,
            'total_materials': total_materials,
            'total_suppliers': total_suppliers,
            'total_customers': total_customers
        }
    })
