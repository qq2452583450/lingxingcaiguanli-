"""
对账蓝图
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


def generate_reconciliation_no():
    """生成对账单号"""
    conn = get_db()
    cursor = conn.cursor()
    year = datetime.now().strftime('%Y')
    cursor.execute("""
        SELECT COUNT(*) FROM reconciliation_statements
        WHERE statement_no LIKE ?
    """, (f'DZD-{year}%',))
    count = cursor.fetchone()[0] + 1
    conn.close()
    return f'DZD-{year}.{count}'


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


reconciliation_bp = Blueprint('reconciliation', __name__, url_prefix='/api')


@reconciliation_bp.route('/reconciliation', methods=['GET'])
def get_reconciliation():
    """获取所有对账单"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT rs.*,
               s.supplier_name, c.customer_name,
               p.project_name
        FROM reconciliation_statements rs
        LEFT JOIN suppliers s ON rs.supplier_id = s.id
        LEFT JOIN customers c ON rs.customer_id = c.id
        LEFT JOIN projects p ON rs.project_id = p.id
        ORDER BY rs.create_time DESC
    """)
    statements = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': statements})


@reconciliation_bp.route('/reconciliation/<int:stmt_id>', methods=['GET'])
def get_reconciliation_detail(stmt_id):
    """获取对账单详情"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT rs.*,
               s.supplier_name, c.customer_name, p.project_name
        FROM reconciliation_statements rs
        LEFT JOIN suppliers s ON rs.supplier_id = s.id
        LEFT JOIN customers c ON rs.customer_id = c.id
        LEFT JOIN projects p ON rs.project_id = p.id
        WHERE rs.id = ?
    """, (stmt_id,))
    row = cursor.fetchone()
    statement = dict(row) if row else None

    cursor.execute("""
        SELECT rd.*, m.material_name, m.specification, u.unit_name
        FROM reconciliation_details rd
        LEFT JOIN materials m ON rd.material_id = m.id
        LEFT JOIN units u ON rd.unit_id = u.id
        WHERE rd.statement_id = ?
    """, (stmt_id,))
    details = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({'success': True, 'data': statement, 'details': details})


@reconciliation_bp.route('/reconciliation', methods=['POST'])
def create_reconciliation():
    """创建对账单"""
    data = request.json
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()

    try:
        statement_no = generate_reconciliation_no()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        details = data.get('details', [])

        total_amount = sum(d.get('amount', 0) for d in details)
        tax_exempt_amount = round(total_amount / 1.01, 2)

        cursor.execute("""
            INSERT INTO reconciliation_statements (
                statement_no, project_id, supplier_id, customer_id,
                contract_no, period_start, period_end,
                total_amount, tax_exempt_amount,
                total_paid, total_invoiced, total_received, balance_due,
                status, create_time, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            statement_no, data.get('project_id'), data.get('supplier_id'),
            data.get('customer_id'), data.get('contract_no', ''),
            data.get('period_start', ''), data.get('period_end', ''),
            total_amount, tax_exempt_amount,
            data.get('total_paid', 0), data.get('total_invoiced', 0),
            data.get('total_received', 0), data.get('balance_due', 0),
            '草稿', now, data.get('remark', '')
        ))
        statement_id = cursor.lastrowid

        for d in details:
            cursor.execute("""
                INSERT INTO reconciliation_details (
                    statement_id, original_no, transaction_date,
                    material_id, specification, unit_id,
                    quantity, unit_price, amount, remark
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                statement_id, d.get('original_no', ''), d.get('transaction_date', ''),
                d.get('material_id'), d.get('specification', ''), d.get('unit_id'),
                d.get('quantity', 0), d.get('unit_price', 0), d.get('amount', 0),
                d.get('remark', '')
            ))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'statement_no': statement_no, 'id': statement_id})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': str(e)})


@reconciliation_bp.route('/reconciliation/<int:stmt_id>/print', methods=['GET'])
def print_reconciliation(stmt_id):
    """打印对账单"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT rs.*, s.supplier_name, c.customer_name, p.project_name
        FROM reconciliation_statements rs
        LEFT JOIN suppliers s ON rs.supplier_id = s.id
        LEFT JOIN customers c ON rs.customer_id = c.id
        LEFT JOIN projects p ON rs.project_id = p.id
        WHERE rs.id = ?
    """, (stmt_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': '对账单不存在'})

    statement = dict(row)

    cursor.execute("""
        SELECT rd.*, m.material_name, m.specification, u.unit_name
        FROM reconciliation_details rd
        LEFT JOIN materials m ON rd.material_id = m.id
        LEFT JOIN units u ON rd.unit_id = u.id
        WHERE rd.statement_id = ?
    """, (stmt_id,))
    details = [dict(row) for row in cursor.fetchall()]

    # 更新打印次数
    cursor.execute("UPDATE reconciliation_statements SET print_count = print_count + 1 WHERE id = ?", (stmt_id,))
    conn.commit()
    conn.close()

    amount_chinese = amount_to_chinese(statement['total_amount'])
    tax_exempt_chinese = amount_to_chinese(statement['tax_exempt_amount'])

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>对账单打印 - {statement['statement_no']}</title>
        <style>
            @page {{ size: A4; margin: 0; }}
            body {{ font-family: "微软雅黑", "Microsoft YaHei", Arial, sans-serif; margin: 0; padding: 20px; }}
            .print-page {{ width: 100%; max-width: 210mm; margin: 0 auto; background: white; }}
            .print-header {{ text-align: center; margin-bottom: 20px; border-bottom: 2px solid #333; padding-bottom: 10px; }}
            .print-header h1 {{ margin: 0 0 5px 0; font-size: 24px; }}
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
        </style>
    </head>
    <body>
        <div class="print-page">
            <div class="print-header">
                <h1>对账单</h1>
                <div>{escape(statement['statement_no'])}</div>
            </div>

            <div class="info-row">
                <div class="info-item"><label>供应商：</label>{escape(statement.get('supplier_name', '-'))}</div>
                <div class="info-item"><label>客户：</label>{escape(statement.get('customer_name', '-'))}</div>
            </div>
            <div class="info-row">
                <div class="info-item"><label>项目：</label>{escape(statement.get('project_name', '-'))}</div>
                <div class="info-item"><label>合同号：</label>{escape(statement.get('contract_no', '-'))}</div>
            </div>
            <div class="info-row">
                <div class="info-item"><label>期间：</label>{escape(statement.get('period_start', '-'))} ~ {escape(statement.get('period_end', '-'))}</div>
                <div class="info-item"><label>状态：</label>{escape(statement.get('status', '-'))}</div>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>序号</th>
                        <th>原始单号</th>
                        <th>日期</th>
                        <th>材料</th>
                        <th>规格</th>
                        <th>单位</th>
                        <th>数量</th>
                        <th>单价</th>
                        <th>金额</th>
                    </tr>
                </thead>
                <tbody>
"""

    for i, d in enumerate(details):
        html += f"""
                    <tr>
                        <td>{i+1}</td>
                        <td>{escape(d.get('original_no', ''))}</td>
                        <td>{escape(d.get('transaction_date', ''))}</td>
                        <td>{escape(d.get('material_name', '-'))}</td>
                        <td>{escape(d.get('specification', '-'))}</td>
                        <td>{escape(d.get('unit_name', '-'))}</td>
                        <td>{d.get('quantity', 0)}</td>
                        <td>¥{d.get('unit_price', 0):.2f}</td>
                        <td>¥{d.get('amount', 0):.2f}</td>
                    </tr>
"""

    html += f"""                </tbody>
            </table>

            <div class="amount-section">
                <div class="amount-row">
                    <span>本期结算金额：<strong>¥{statement.get('total_amount', 0):.2f}</strong></span>
                    <span>本期不含税金额：¥{statement.get('tax_exempt_amount', 0):.2f}</span>
                </div>
                <div class="amount-row">
                    <span>累计已付款：¥{statement.get('total_paid', 0):.2f}</span>
                    <span>累计已开票：¥{statement.get('total_invoiced', 0):.2f}</span>
                </div>
                <div class="amount-row">
                    <span>累计已收款：¥{statement.get('total_received', 0):.2f}</span>
                    <span>截止本次尚欠：¥{statement.get('balance_due', 0):.2f}</span>
                </div>
                <div class="amount-chinese">结算金额大写：{amount_chinese}</div>
                <div style="font-size: 14px; color: #666; margin-top: 5px;">不含税金额大写：{tax_exempt_chinese}</div>
            </div>

            <div class="signatures">
                <div class="signature-item">
                    <div class="signature-line">供应商签章</div>
                </div>
                <div class="signature-item">
                    <div class="signature-line">客户签章</div>
                </div>
                <div class="signature-item">
                    <div class="signature-line">财务复核</div>
                </div>
                <div class="signature-item">
                    <div class="signature-line">负责人</div>
                </div>
            </div>

            <div style="margin-top: 20px; font-size: 10px; color: #999; text-align: right;">
                打印时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 第{statement.get('print_count', 0) + 1}次打印
            </div>
        </div>
    </body>
    </html>
    """

    response = make_response(html)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response