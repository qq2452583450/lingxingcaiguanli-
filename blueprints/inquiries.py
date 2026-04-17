"""
询价单蓝图
"""
from flask import Blueprint, request, jsonify, session, make_response
import sqlite3
import config
from datetime import datetime
from html import escape

inquiry_bp = Blueprint('inquiries', __name__, url_prefix='/api')


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def generate_inquiry_no():
    """生成询价单号"""
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y%m%d')
    cursor.execute("""
        SELECT COUNT(*) FROM purchase_inquiries
        WHERE inquiry_no LIKE ?
    """, (f'CGXJ-{today[:2]}-{today[2:]}%',))
    count = cursor.fetchone()[0] + 1
    conn.close()
    return f'CGXJ-{today[2:]}-{str(count).zfill(3)}'


@inquiry_bp.route('/purchase-inquiries', methods=['GET'])
def get_inquiries():
    """获取所有询价单"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pi.*, u.real_name as applicant_name
        FROM purchase_inquiries pi
        LEFT JOIN users u ON pi.applicant_id = u.id
        ORDER BY pi.create_time DESC
    """)
    inquiries = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': inquiries})


@inquiry_bp.route('/purchase-inquiries/<int:inquiry_id>', methods=['GET'])
def get_inquiry(inquiry_id):
    """获取询价单详情"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pi.*, u.real_name as applicant_name
        FROM purchase_inquiries pi
        LEFT JOIN users u ON pi.applicant_id = u.id
        WHERE pi.id = ?
    """, (inquiry_id,))
    row = cursor.fetchone()
    inquiry = dict(row) if row else None

    cursor.execute("""
        SELECT pd.*, m.material_name, m.specification, m.material_code,
               u.unit_name, s.supplier_name
        FROM purchase_inquiry_details pd
        LEFT JOIN materials m ON pd.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        LEFT JOIN suppliers s ON pd.supplier_id = s.id
        WHERE pd.inquiry_id = ?
    """, (inquiry_id,))
    details = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({'success': True, 'data': inquiry, 'details': details})


@inquiry_bp.route('/purchase-inquiries', methods=['POST'])
def create_inquiry():
    """创建询价单"""
    data = request.json
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()

    try:
        inquiry_no = generate_inquiry_no()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        details = data.get('details', [])

        total_amount = sum(d.get('this_price', 0) * d.get('quantity', 1) for d in details)
        is_below = 1 if any(d.get('this_price', 0) < d.get('library_price', 0) for d in details) else 0

        cursor.execute("""
            INSERT INTO purchase_inquiries (
                inquiry_no, inquiry_date, applicant_id, total_amount,
                is_below_library_price, approval_status, create_time, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            inquiry_no, data.get('inquiry_date', now[:10]),
            user['id'], total_amount, is_below, '待审批', now, data.get('remark', '')
        ))
        inquiry_id = cursor.lastrowid

        for d in details:
            is_lowest = 1 if d.get('this_price', 0) <= d.get('library_price', 0) else 0
            price_diff = d.get('this_price', 0) - d.get('library_price', 0)
            cursor.execute("""
                INSERT INTO purchase_inquiry_details (
                    inquiry_id, material_id, supplier_id, this_price,
                    library_price, is_lowest, price_diff, quantity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                inquiry_id, d.get('material_id'), d.get('supplier_id'),
                d.get('this_price', 0), d.get('library_price', 0),
                is_lowest, price_diff, d.get('quantity', 1)
            ))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'inquiry_no': inquiry_no, 'id': inquiry_id})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': str(e)})


@inquiry_bp.route('/purchase-inquiries/<int:inquiry_id>/approve', methods=['POST'])
def approve_inquiry(inquiry_id):
    """审批询价单"""
    data = request.json
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    action = data.get('action')
    remark = data.get('remark', '')

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if action == 'reject':
        cursor.execute("""
            UPDATE purchase_inquiries
            SET approval_status = '已驳回', approver_id = ?, approve_time = ?, approval_remark = ?
            WHERE id = ? AND approval_status IN ('待审批', '材料员已审')
        """, (user['id'], now, remark, inquiry_id))
    elif action == 'material_clerk':
        cursor.execute("""
            UPDATE purchase_inquiries
            SET approval_status = '材料员已审', approver_id = ?, approve_time = ?, approval_remark = ?
            WHERE id = ? AND approval_status = '待审批'
        """, (user['id'], now, remark, inquiry_id))
    elif action == 'manager':
        cursor.execute("""
            UPDATE purchase_inquiries
            SET approval_status = '已同意', approver_id = ?, approve_time = ?, approval_remark = ?
            WHERE id = ? AND approval_status = '材料员已审'
        """, (user['id'], now, remark, inquiry_id))
        cursor.execute("SELECT * FROM purchase_inquiry_details WHERE inquiry_id = ? AND is_lowest = 1", (inquiry_id,))
        for d in cursor.fetchall():
            tax_price = d['this_price']
            tax_exempt = round(tax_price / 1.01, 2)
            cursor.execute("UPDATE materials SET tax_price = ?, tax_exempt_price = ? WHERE id = ?",
                          (tax_price, tax_exempt, d['material_id']))
        cursor.execute("UPDATE purchase_inquiries SET library_price_updated = 1 WHERE id = ?", (inquiry_id,))
    else:
        conn.close()
        return jsonify({'success': False, 'message': '无效的操作'})

    if cursor.rowcount == 0:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': '操作失败，状态已更新'})

    result_text = {'reject': '驳回', 'material_clerk': '材料员同意', 'manager': '主管同意'}.get(action, action)
    cursor.execute("""
        INSERT INTO approval_records (order_type, order_id, approver_id, approver_name, result, remark, approval_time)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ('purchase_inquiry', inquiry_id, user['id'], user['real_name'], result_text, remark, now))

    conn.commit()
    conn.close()
    return jsonify({'success': True})


@inquiry_bp.route('/purchase-inquiries/<int:inquiry_id>/approval-history', methods=['GET'])
def get_inquiry_approval_history(inquiry_id):
    """获取询价单审批历史"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ar.*, u.real_name as approver_real_name
        FROM approval_records ar
        LEFT JOIN users u ON ar.approver_id = u.id
        WHERE ar.order_type = 'purchase_inquiry' AND ar.order_id = ?
        ORDER BY ar.approval_time ASC
    """, (inquiry_id,))
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'data': records})


@inquiry_bp.route('/purchase-inquiries/<int:inquiry_id>/approval-print', methods=['GET'])
def print_inquiry_approval(inquiry_id):
    """打印询价单审批签字单"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pi.*, u.real_name as applicant_name
        FROM purchase_inquiries pi
        LEFT JOIN users u ON pi.applicant_id = u.id
        WHERE pi.id = ?
    """, (inquiry_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': '单据不存在'})

    inquiry = dict(row)

    cursor.execute("""
        SELECT pd.*, m.material_name, m.specification, m.material_code, u.unit_name, s.supplier_name
        FROM purchase_inquiry_details pd
        LEFT JOIN materials m ON pd.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        LEFT JOIN suppliers s ON pd.supplier_id = s.id
        WHERE pd.inquiry_id = ?
    """, (inquiry_id,))
    details = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT ar.*, u.real_name as approver_real_name
        FROM approval_records ar
        LEFT JOIN users u ON ar.approver_id = u.id
        WHERE ar.order_type = 'purchase_inquiry' AND ar.order_id = ?
        ORDER BY ar.approval_time ASC
    """, (inquiry_id,))
    approval_records = [dict(row) for row in cursor.fetchall()]

    conn.close()

    amount_chinese = amount_to_chinese(inquiry['total_amount'])

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>询价单审批签字单 - {inquiry['inquiry_no']}</title>
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
            .approval-section {{ margin-top: 30px; }}
            .approval-title {{ font-size: 16px; font-weight: bold; margin-bottom: 15px; border-bottom: 1px solid #333; padding-bottom: 5px; }}
            .approval-table {{ margin-bottom: 20px; }}
            .approval-item {{ display: flex; border-bottom: 1px dashed #ccc; padding: 10px 0; }}
            .approval-level {{ width: 80px; font-weight: bold; }}
            .approval-content {{ flex: 1; }}
            .approval-name {{ font-weight: bold; margin-bottom: 5px; }}
            .approval-result {{ color: #27ae60; margin: 3px 0; }}
            .approval-remark {{ color: #666; font-size: 11px; margin: 3px 0; }}
            .approval-time {{ color: #999; font-size: 10px; }}
            .pending-approval {{ color: #f39c12; font-style: italic; }}
            .signatures {{ display: flex; justify-content: space-between; margin-top: 40px; }}
            .signature-item {{ text-align: center; width: 20%; }}
            .signature-line {{ border-top: 1px solid #333; margin-top: 40px; padding-top: 5px; }}
            .amount-chinese {{ font-size: 18px; font-weight: bold; color: #c0392b; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <div class="print-page">
            <div class="print-header">
                <h1>采购询比价审批签字单</h1>
                <div>{escape(inquiry['inquiry_no'])}</div>
            </div>

            <div class="info-row">
                <div class="info-item"><label>申请日期：</label>{escape(inquiry.get('inquiry_date', '-'))}</div>
                <div class="info-item"><label>申请人：</label>{escape(inquiry.get('applicant_name', '-'))}</div>
            </div>
            <div class="info-row">
                <div class="info-item"><label>当前状态：</label><strong>{escape(inquiry.get('approval_status', '-'))}</strong></div>
                <div class="info-item"><label>低于库内价：</label>{'是' if inquiry.get('is_below_library_price') == 1 else '否'}</div>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>序号</th>
                        <th>编码</th>
                        <th>名称</th>
                        <th>规格</th>
                        <th>单位</th>
                        <th>供应商</th>
                        <th>库内价</th>
                        <th>本次报价</th>
                        <th>差额</th>
                    </tr>
                </thead>
                <tbody>
"""

    for i, d in enumerate(details):
        html += f"""
                    <tr>
                        <td>{i+1}</td>
                        <td>{escape(d.get('material_code', ''))}</td>
                        <td>{escape(d.get('material_name', ''))}</td>
                        <td>{escape(d.get('specification', '-'))}</td>
                        <td>{escape(d.get('unit_name', '-'))}</td>
                        <td>{escape(d.get('supplier_name', '-'))}</td>
                        <td>¥{d.get('library_price', 0):.2f}</td>
                        <td>¥{d.get('this_price', 0):.2f}</td>
                        <td style="color: {'#e74c3c' if d.get('price_diff', 0) < 0 else '#27ae60'}">¥{d.get('price_diff', 0):.2f}</td>
                    </tr>
"""

    html += f"""                </tbody>
            </table>

            <div style="text-align: right; margin: 15px 0;">
                <strong>总金额：¥{inquiry.get('total_amount', 0):.2f}</strong>
                <div class="amount-chinese">大写：{amount_chinese}</div>
            </div>

            <div class="approval-section">
                <div class="approval-title">审批记录</div>
                <table class="approval-table">
                    <thead>
                        <tr>
                            <th style="width: 100px;">审批级别</th>
                            <th>审批人</th>
                            <th>结果</th>
                            <th>备注</th>
                            <th style="width: 150px;">时间</th>
                        </tr>
                    </thead>
                    <tbody>
"""

    approval_levels = [
        {'level': '材料员', 'status': '材料员已审', 'key': 'material_clerk'},
        {'level': '部门主管', 'status': '已同意', 'key': 'manager'},
    ]

    for level_info in approval_levels:
        found = next((r for r in approval_records if level_info['key'] in r.get('result', '').lower()), None)
        if found:
            html += f"""
                        <tr>
                            <td>{level_info['level']}</td>
                            <td>{escape(found.get('approver_name', '-'))}</td>
                            <td style="color: #27ae60;">{escape(found.get('result', '-'))}</td>
                            <td>{escape(found.get('remark', '-'))}</td>
                            <td>{escape(found.get('approval_time', '-'))}</td>
                        </tr>
"""
        else:
            next_level_pending = next((r for r in approval_records if level_info['status'] == '待审批'), None)
            if inquiry['approval_status'] == level_info['status'] or (inquiry['approval_status'] == '待审批' and level_info['level'] == '材料员'):
                html += f"""
                        <tr>
                            <td>{level_info['level']}</td>
                            <td colspan="4" class="pending-approval">待审批</td>
                        </tr>
"""

    html += f"""                    </tbody>
                </table>
            </div>

            <div style="margin-top: 30px; font-size: 12px; color: #666;">
                <strong>备注：</strong>{escape(inquiry.get('remark') or '无')}
            </div>

            <div class="signatures">
                <div class="signature-item">
                    <div class="signature-line">申请人</div>
                </div>
                <div class="signature-item">
                    <div class="signature-line">材料员签字</div>
                </div>
                <div class="signature-item">
                    <div class="signature-line">主管签字</div>
                </div>
                <div class="signature-item">
                    <div class="signature-line">日期</div>
                </div>
            </div>

            <div style="margin-top: 20px; font-size: 10px; color: #999; text-align: right;">
                打印时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
        </div>
    </body>
    </html>
    """

    response = make_response(html)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response


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
