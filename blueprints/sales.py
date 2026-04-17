"""
销售蓝图
"""
from flask import Blueprint, request, jsonify, session, make_response
import sqlite3
import config
from datetime import datetime
from html import escape


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def generate_sales_no():
    """生成销售单号"""
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y%m%d')
    cursor.execute("SELECT COUNT(*) FROM sales_orders WHERE order_no LIKE ?", (f'XS-{today}%',))
    count = cursor.fetchone()[0] + 1
    conn.close()
    return f'XS-{today}-{str(count).zfill(4)}'


def amount_to_chinese(amount):
    """金额转大写"""
    if amount is None:
        amount = 0
    amount = round(float(amount), 2)
    integer_part = int(amount)
    decimal_part = round((amount - integer_part) * 100)

    chinese_digits = ['零', '壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖']
    chinese_units = ['', '拾', '佰', '仟', '万', '拾', '佰', '仟', '亿']

    if integer_part == 0:
        result = '零'
    else:
        result = ''
        str_int = str(integer_part)
        length = len(str_int)
        for i, digit in enumerate(str_int):
            digit_int = int(digit)
            unit_index = length - i - 1
            if digit_int != 0:
                result += chinese_digits[digit_int] + chinese_units[unit_index]
            else:
                if unit_index % 4 == 0 and result and result[-1] != '零' and result[-1] != '万' and result[-1] != '亿':
                    if length > 4 and (length - i) <= length % 4 or result.endswith('亿'):
                        pass
                    else:
                        result += '零'
                elif result and result[-1] != '零' and result[-1] != '万' and result[-1] != '亿':
                    result += '零'

        result = result.rstrip('零')
        if result.endswith('零'):
            result = result[:-1]

    if decimal_part == 0:
        return f"{result}元整"
    else:
        result += f"元{chinese_digits[decimal_part // 10] if decimal_part >= 10 else '零'}{chinese_digits[decimal_part % 10 if decimal_part >= 10 else decimal_part]}角"
        if decimal_part % 10 == 0:
            result = result.rstrip('零角') + '整'
        return result


sales_bp = Blueprint('sales', __name__, url_prefix='/api')


@sales_bp.route('/sales', methods=['GET'])
def get_sales():
    """获取所有销售单"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, u.real_name as salesperson_name, c.customer_name
        FROM sales_orders s
        LEFT JOIN users u ON s.salesperson_id = u.id
        LEFT JOIN customers c ON s.customer_id = c.id
        ORDER BY s.create_time DESC
    """)
    sales = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': sales})


@sales_bp.route('/sales/<int:sale_id>', methods=['GET'])
def get_sale(sale_id):
    """获取销售单详情"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, u.real_name as salesperson_name, c.customer_name
        FROM sales_orders s
        LEFT JOIN users u ON s.salesperson_id = u.id
        LEFT JOIN customers c ON s.customer_id = c.id
        WHERE s.id = ?
    """, (sale_id,))
    row = cursor.fetchone()
    sale = dict(row) if row else None

    cursor.execute("""
        SELECT sd.*, m.material_name, m.specification, m.material_code, u.unit_name
        FROM sales_order_details sd
        LEFT JOIN materials m ON sd.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        WHERE sd.order_id = ?
    """, (sale_id,))
    details = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({'success': True, 'data': sale, 'details': details})


@sales_bp.route('/sales', methods=['POST'])
def create_sale():
    """创建销售单"""
    data = request.json
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()

    try:
        order_no = generate_sales_no()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        details = data.get('details', [])

        total_amount = sum(d.get('unit_price', 0) * d.get('quantity', 0) for d in details)

        cursor.execute("""
            INSERT INTO sales_orders (
                order_no, order_type, customer_id, customer_name,
                total_amount, received_amount, payment_status,
                salesperson_id, create_time, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_no, data.get('order_type', '零售'), data.get('customer_id'),
            data.get('customer_name', ''), total_amount, data.get('received_amount', 0),
            '未付款', user['id'], now, data.get('remark', '')
        ))
        order_id = cursor.lastrowid

        for d in details:
            amount = d.get('quantity', 0) * d.get('unit_price', 0)
            cursor.execute("""
                INSERT INTO sales_order_details (order_id, material_id, quantity, unit_price, amount)
                VALUES (?, ?, ?, ?, ?)
            """, (order_id, d.get('material_id'), d.get('quantity', 0),
                  d.get('unit_price', 0), amount))

            # 扣减库存
            cursor.execute("""
                UPDATE inventory SET quantity = quantity - ?,
                update_time = ? WHERE material_id = ? AND warehouse_id = ?
            """, (d.get('quantity', 0), now, d.get('material_id'), data.get('warehouse_id', 1)))

            # 出库记录
            cursor.execute("""
                INSERT INTO stock_out_orders (order_no, out_type, customer_name, warehouse_id, operator_id, out_time, create_time)
                VALUES (?, '销售', ?, ?, ?, ?, ?)
            """, (order_no, data.get('customer_name', ''), data.get('warehouse_id', 1),
                  user['id'], now, now))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'order_no': order_no, 'id': order_id})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': str(e)})


@sales_bp.route('/sales/<int:sale_id>/print', methods=['GET'])
def print_sale(sale_id):
    """三联打印销售单"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.*, u.real_name as salesperson_name, c.customer_name, c.phone as customer_phone, c.address as customer_address
        FROM sales_orders s
        LEFT JOIN users u ON s.salesperson_id = u.id
        LEFT JOIN customers c ON s.customer_id = c.id
        WHERE s.id = ?
    """, (sale_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': '单据不存在'})
    sale = dict(row)

    cursor.execute("""
        SELECT sd.*, m.material_name, m.specification, m.material_code, u.unit_name
        FROM sales_order_details sd
        LEFT JOIN materials m ON sd.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        WHERE sd.order_id = ?
    """, (sale_id,))
    details = [dict(row) for row in cursor.fetchall()]

    # 更新打印次数
    cursor.execute("UPDATE sales_orders SET print_count = print_count + 1 WHERE id = ?", (sale_id,))
    conn.commit()
    conn.close()

    # 生成三联打印HTML
    amount_chinese = amount_to_chinese(sale['total_amount'])

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>销售单打印 - {sale['order_no']}</title>
        <style>
            @page {{ size: A4; margin: 0; }}
            body {{ font-family: "微软雅黑", "Microsoft YaHei", Arial, sans-serif; margin: 0; padding: 20px; }}
            .print-page {{ width: 100%; max-width: 210mm; margin: 0 auto; background: white; }}
            .print-header {{ text-align: center; margin-bottom: 20px; border-bottom: 2px solid #333; padding-bottom: 10px; }}
            .print-header h1 {{ margin: 0 0 5px 0; font-size: 24px; }}
            .copy-label {{ font-size: 14px; color: #666; margin-top: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
            th, td {{ border: 1px solid #333; padding: 8px; font-size: 12px; }}
            th {{ background: #f0f0f0; }}
            .info-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 15px; }}
            .info-item {{ flex: 1; min-width: 200px; }}
            .info-item label {{ font-weight: bold; }}
            .amount-section {{ margin-top: 20px; border-top: 2px solid #333; padding-top: 15px; }}
            .amount-row {{ display: flex; justify-content: space-between; margin: 10px 0; }}
            .amount-chinese {{ font-size: 18px; font-weight: bold; color: #c0392b; margin-top: 10px; }}
            .signatures {{ display: flex; justify-content: space-between; margin-top: 40px; }}
            .signature-item {{ text-align: center; width: 20%; }}
            .signature-line {{ border-top: 1px solid #333; margin-top: 40px; padding-top: 5px; }}
            .three-copies {{ display: flex; flex-direction: column; gap: 30px; }}
            .copy-white {{ background: white; }}
            .copy-red {{ background: #fff5f5; }}
            .copy-yellow {{ background: #fffef5; }}
            @media print {{
                .three-copies {{ gap: 0; }}
                .copy-white {{ page-break-before: always; }}
            }}
        </style>
    </head>
    <body>
        <div class="three-copies">
            <!-- 白联 - 留存 -->
            <div class="print-page copy-white">
                <div class="print-header">
                    <h1>销售单（白联）</h1>
                    <div class="copy-label">第一联：留存</div>
                </div>
                {build_print_content(sale, details, amount_chinese)}
            </div>
            <!-- 红联 - 客户 -->
            <div class="print-page copy-red">
                <div class="print-header">
                    <h1>销售单（红联）</h1>
                    <div class="copy-label">第二联：客户</div>
                </div>
                {build_print_content(sale, details, amount_chinese)}
            </div>
            <!-- 黄联 - 财务 -->
            <div class="print-page copy-yellow">
                <div class="print-header">
                    <h1>销售单（黄联）</h1>
                    <div class="copy-label">第三联：财务</div>
                </div>
                {build_print_content(sale, details, amount_chinese)}
            </div>
        </div>
    </body>
    </html>
    """

    response = make_response(html)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response


def build_print_content(sale, details, amount_chinese):
    """构建打印内容"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    details_html = ''
    for i, d in enumerate(details):
        details_html += f"""
        <tr>
            <td>{i+1}</td>
            <td>{escape(d.get('material_code', ''))}</td>
            <td>{escape(d.get('material_name', ''))}</td>
            <td>{escape(d.get('specification', '-'))}</td>
            <td>{escape(d.get('unit_name', '-'))}</td>
            <td>{d.get('quantity', 0)}</td>
            <td>¥{d.get('unit_price', 0):.2f}</td>
            <td>¥{d.get('amount', 0):.2f}</td>
        </tr>
        """

    return f"""
    <div class="info-row">
        <div class="info-item"><label>单号：</label>{escape(sale.get('order_no', ''))}</div>
        <div class="info-item"><label>日期：</label>{escape(sale.get('create_time', '')[:10] if sale.get('create_time') else '')}</div>
    </div>
    <div class="info-row">
        <div class="info-item"><label>客户：</label>{escape(sale.get('customer_name', '-'))}</div>
        <div class="info-item"><label>电话：</label>{escape(sale.get('customer_phone', '-'))}</div>
    </div>
    <div class="info-row">
        <div class="info-item"><label>地址：</label>{escape(sale.get('customer_address', '-'))}</div>
        <div class="info-item"><label>销售员：</label>{escape(sale.get('salesperson_name', '-'))}</div>
    </div>
    <div class="info-row">
        <div class="info-item"><label>类型：</label>{escape(sale.get('order_type', '零售'))}</div>
    </div>

    <table>
        <thead>
            <tr>
                <th>序号</th>
                <th>编码</th>
                <th>名称</th>
                <th>规格</th>
                <th>单位</th>
                <th>数量</th>
                <th>单价</th>
                <th>金额</th>
            </tr>
        </thead>
        <tbody>
            {details_html}
        </tbody>
    </table>

    <div class="amount-section">
        <div class="amount-row">
            <span>总金额：<strong>¥{sale.get('total_amount', 0):.2f}</strong></span>
            <span>已收款：¥{sale.get('received_amount', 0):.2f}</span>
        </div>
        <div class="amount-chinese">大写：{amount_chinese}</div>
    </div>

    <div class="signatures">
        <div class="signature-item">
            <div class="signature-line">制单人</div>
        </div>
        <div class="signature-item">
            <div class="signature-line">复核人</div>
        </div>
        <div class="signature-item">
            <div class="signature-line">负责人</div>
        </div>
        <div class="signature-item">
            <div class="signature-line">客户签收</div>
        </div>
    </div>

    <div style="margin-top: 20px; font-size: 10px; color: #999; text-align: right;">
        打印时间：{now} | 第{sale.get('print_count', 0) + 1}次打印
    </div>
    """