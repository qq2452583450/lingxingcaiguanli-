"""
对账蓝图
"""
from flask import Blueprint, request, jsonify, session, make_response
from datetime import datetime
from html import escape
from helpers import amount_to_chinese, get_db


def generate_reconciliation_no(project_id=None, supplier_id=None):
    """生成对账单号: DZD-项目名-供应商-00X"""
    conn = get_db()
    cursor = conn.cursor()

    # 获取项目名简称
    project_name = ''
    if project_id:
        cursor.execute("SELECT project_name FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        if row:
            project_name = row['project_name'] if isinstance(row, dict) else row[0]

    # 获取供应商简称
    supplier_name = ''
    if supplier_id:
        cursor.execute("SELECT supplier_name FROM suppliers WHERE id = ?", (supplier_id,))
        row = cursor.fetchone()
        if row:
            supplier_name = row['supplier_name'] if isinstance(row, dict) else row[0]

    # 构建前缀
    prefix_parts = ['DZD']
    if project_name:
        prefix_parts.append(project_name)
    if supplier_name:
        prefix_parts.append(supplier_name)
    prefix = '-'.join(prefix_parts)

    # 查找同前缀的最大序号
    cursor.execute("""
        SELECT statement_no FROM reconciliation_statements
        WHERE statement_no LIKE ?
        ORDER BY statement_no DESC LIMIT 1
    """, (f'{prefix}-%',))
    row = cursor.fetchone()

    if row:
        last_no = row['statement_no'] if isinstance(row, dict) else row[0]
        try:
            seq = int(last_no.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1

    conn.close()
    return f'{prefix}-{seq:03d}'


reconciliation_bp = Blueprint('reconciliation', __name__, url_prefix='/api')


def safe_escape(val, default='-'):
    """安全转义HTML，处理None值"""
    if val is None:
        return default
    return escape(str(val))


@reconciliation_bp.route('/reconciliation/supplier-purchases', methods=['GET'])
def get_supplier_purchases():
    """根据供应商+周期查询已审批的采购明细（选定报价）"""
    supplier_id = request.args.get('supplier_id')
    period_start = request.args.get('period_start')
    period_end = request.args.get('period_end')

    if not supplier_id:
        return jsonify({'success': True, 'data': []})

    conn = get_db()
    cursor = conn.cursor()

    # 查询该供应商在指定周期内，已审批通过询价单中的选定报价明细
    sql = """
        SELECT 
            pi.id AS inquiry_id,
            pi.inquiry_no,
            pi.inquiry_date,
            pi.create_time AS inquiry_create_time,
            pii.material_id,
            m.material_name,
            m.specification,
            u.unit_name,
            pii.quantity,
            pii.library_price,
            piq.tax_price,
            piq.total_amount,
            piq.supplier_id,
            s.supplier_name
        FROM purchase_inquiry_quotes piq
        JOIN purchase_inquiry_items pii ON piq.item_id = pii.id
        JOIN purchase_inquiries pi ON pii.inquiry_id = pi.id
        LEFT JOIN materials m ON pii.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        LEFT JOIN suppliers s ON piq.supplier_id = s.id
        WHERE piq.is_selected = 1
          AND piq.supplier_id = ?
          AND pi.approval_status = '已同意'
    """
    params = [supplier_id]

    if period_start:
        sql += " AND pi.inquiry_date >= ?"
        params.append(period_start)
    if period_end:
        sql += " AND pi.inquiry_date <= ?"
        params.append(period_end)

    sql += " ORDER BY pi.inquiry_date, pi.inquiry_no"

    cursor.execute(sql, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({'success': True, 'data': rows})


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
        statement_no = generate_reconciliation_no(
            project_id=data.get('project_id'),
            supplier_id=data.get('supplier_id')
        )
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        details = data.get('details', [])
        tax_rate = data.get('tax_rate', 0.01)

        total_amount = sum(d.get('amount', 0) for d in details)
        tax_exempt_amount = round(total_amount / (1 + tax_rate), 2)

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
                    material_id, material_name, specification, unit_id, unit_name,
                    quantity, unit_price, amount, remark
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                statement_id, d.get('original_no', ''), d.get('transaction_date', ''),
                d.get('material_id'), d.get('material_name', ''), d.get('specification', ''),
                d.get('unit_id'), d.get('unit_name', ''),
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


@reconciliation_bp.route('/reconciliation/<int:stmt_id>/confirm', methods=['POST'])
def confirm_reconciliation(stmt_id):
    """确认对账单（草稿→已确认）"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM reconciliation_statements WHERE id = ?", (stmt_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': '对账单不存在'})

    current_status = dict(row)['status']
    if current_status != '草稿':
        conn.close()
        return jsonify({'success': False, 'message': f'当前状态为"{current_status}"，只有草稿状态才能确认'})

    cursor.execute("UPDATE reconciliation_statements SET status = '已确认' WHERE id = ?", (stmt_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': '对账单已确认'})


@reconciliation_bp.route('/reconciliation/<int:stmt_id>', methods=['DELETE'])
def delete_reconciliation(stmt_id):
    """删除对账单（仅草稿可删）"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM reconciliation_statements WHERE id = ?", (stmt_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': '对账单不存在'})

    current_status = dict(row)['status']
    if current_status != '草稿':
        conn.close()
        return jsonify({'success': False, 'message': f'当前状态为"{current_status}"，只有草稿状态才能删除'})

    cursor.execute("DELETE FROM reconciliation_details WHERE statement_id = ?", (stmt_id,))
    cursor.execute("DELETE FROM reconciliation_statements WHERE id = ?", (stmt_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': '对账单已删除'})


@reconciliation_bp.route('/reconciliation/<int:stmt_id>/print', methods=['GET'])
def print_reconciliation(stmt_id):
    """打印对账单 - 严格按照零星材对账单.xlsx模板生成"""
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

    # 更新打印次数并更新状态为"已打印"
    new_status = '已打印' if statement.get('status') == '已确认' else statement.get('status', '草稿')
    cursor.execute("UPDATE reconciliation_statements SET print_count = print_count + 1, status = ? WHERE id = ?", (new_status, stmt_id))
    conn.commit()
    conn.close()

    total_amount = statement.get('total_amount') or 0
    tax_rate = statement.get('tax_rate') or 0.01
    tax_exempt_amount = total_amount / (1 + tax_rate) if total_amount else 0
    prev_total = statement.get('previous_total') or 0
    cumulative_amount = total_amount + prev_total

    amount_chinese = amount_to_chinese(total_amount)
    period_start = statement.get('period_start') or ''
    period_end = statement.get('period_end') or ''
    period_display = f"{period_start} ~ {period_end}" if period_start and period_end else ''

    # 对账截止日（用于供方确认）
    end_year = period_end[:4] if len(period_end) >= 4 else ''
    end_month = period_end[5:7] if len(period_end) >= 7 else ''
    end_day = period_end[8:10] if len(period_end) >= 10 else ''

    # 计算数量合计和金额合计
    total_qty = sum(d.get('quantity') or 0 for d in details)
    total_amt = sum(d.get('amount') or 0 for d in details)

    # 生成明细行
    detail_rows = ''
    for i, d in enumerate(details):
        detail_rows += f"""
                    <tr>
                        <td>{i+1}</td>
                        <td>{safe_escape(d.get('transaction_date'), '')}</td>
                        <td>{safe_escape(d.get('original_no'), '')}</td>
                        <td>{safe_escape(d.get('material_name'))}</td>
                        <td>{safe_escape(d.get('specification'), '')}</td>
                        <td>{safe_escape(d.get('unit_name'), '')}</td>
                        <td>{d.get('quantity', 0)}</td>
                        <td>{d.get('unit_price', 0):.2f}</td>
                        <td>{d.get('amount', 0):.2f}</td>
                        <td>{safe_escape(d.get('remark'), '')}</td>
                    </tr>"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>零星材料对账单 - {safe_escape(statement['statement_no'], '')}</title>
        <style>
            @page {{ size: A4; margin: 10mm 8mm; }}
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: "宋体", SimSun, serif; font-size: 11px; color: #000; line-height: 1.5; }}
            .page {{ width: 100%; }}

            /* 标题 */
            .title {{ text-align: center; font-size: 18px; font-weight: bold; letter-spacing: 4px; margin-bottom: 4px; }}

            /* 信息区 - 用表格布局严格对齐 */
            .info-table {{ width: 100%; border-collapse: collapse; margin-bottom: 2px; }}
            .info-table td {{ padding: 3px 4px; font-size: 11px; border: none; }}
            .info-label {{ white-space: nowrap; font-weight: normal; }}
            .info-value {{ border-bottom: 1px solid #333; padding: 0 8px; min-width: 60px; }}

            /* 明细表格 */
            table.detail {{ width: 100%; border-collapse: collapse; margin: 0; }}
            table.detail th, table.detail td {{ border: 1px solid #000; padding: 4px 5px; font-size: 11px; text-align: center; line-height: 1.4; }}
            table.detail th {{ background: #f5f5f5; font-weight: bold; font-size: 11px; }}
            table.detail td:nth-child(2) {{ white-space: nowrap; }}
            table.detail td:nth-child(8),
            table.detail td:nth-child(9) {{ text-align: right; padding-right: 8px; }}
            .subtotal-label {{ text-align: left; font-weight: bold; padding-left: 8px; }}

            /* 金额区域 */
            .amount-table {{ width: 100%; border-collapse: collapse; margin-top: 2px; }}
            .amount-table td {{ border: 1px solid #000; padding: 3px 5px; font-size: 11px; line-height: 1.4; }}
            .amount-label {{ font-weight: bold; white-space: nowrap; }}
            .amount-value {{ text-align: right; padding-right: 8px; }}
            .amount-cn {{ text-align: left; }}

            /* 供方确认 */
            .supplier-confirm {{ margin-top: 3px; border: 1px solid #000; padding: 5px 8px; font-size: 11px; line-height: 1.6; }}
            .supplier-confirm .confirm-title {{ font-weight: bold; }}

            /* 审批签字表 */
            .sign-table {{ width: 100%; border-collapse: collapse; margin-top: 4px; }}
            .sign-table th, .sign-table td {{ border: 1px solid #000; padding: 4px 6px; font-size: 11px; }}
            .sign-table th {{ background: #f5f5f5; font-weight: bold; text-align: center; height: 22px; }}
            .sign-table td {{ height: 32px; vertical-align: middle; }}

            /* 备注 */
            .notes {{ margin-top: 3px; font-size: 10px; line-height: 1.5; color: #333; }}
            .notes-title {{ font-weight: bold; }}

            @media print {{
                body {{ margin: 0; padding: 0; }}
                .no-print {{ display: none; }}
            }}
        </style>
    </head>
    <body>
        <div class="page">
            <!-- 标题 -->
            <div class="title">零星材料对账单</div>

            <!-- 基本信息区 -->
            <table class="info-table">
                <tr>
                    <td class="info-label">供货单位名称：</td>
                    <td class="info-value" style="width:35%;">{safe_escape(statement.get('supplier_name'))}</td>
                    <td style="width:8%;"></td>
                    <td class="info-label">对账编号：</td>
                    <td class="info-value" style="width:30%;">{safe_escape(statement.get('statement_no'), '')}</td>
                </tr>
                <tr>
                    <td class="info-label">购货单位名称：</td>
                    <td class="info-value">{safe_escape(statement.get('customer_name'), '中天建设集团有限公司')}</td>
                    <td></td>
                    <td class="info-label">合同编号：</td>
                    <td class="info-value">{safe_escape(statement.get('contract_no'), '')}</td>
                </tr>
                <tr>
                    <td class="info-label">项目名称：</td>
                    <td class="info-value">{safe_escape(statement.get('project_name'))}</td>
                    <td></td>
                    <td class="info-label">对账周期：</td>
                    <td class="info-value">{safe_escape(period_display, '')}</td>
                </tr>
            </table>
            <div style="text-align:right; font-size:9px; margin-bottom:0; margin-top:0;">单位：元</div>

            <!-- 对账明细表 -->
            <table class="detail">
                <thead>
                    <tr>
                        <th style="width:5%;">序号</th>
                        <th style="width:10%;">日期</th>
                        <th style="width:12%;">原始单号</th>
                        <th style="width:14%;">材料名称</th>
                        <th style="width:10%;">规格型号</th>
                        <th style="width:6%;">单位</th>
                        <th style="width:7%;">数量</th>
                        <th style="width:9%;">单价</th>
                        <th style="width:11%;">金额</th>
                        <th style="width:10%;">备注</th>
                    </tr>
                </thead>
                <tbody>
                    {detail_rows}
                    <tr>
                        <td colspan="6" class="subtotal-label">合计（小计）</td>
                        <td>{total_qty}</td>
                        <td></td>
                        <td style="text-align:right; padding-right:8px;">{total_amt:.2f}</td>
                        <td></td>
                    </tr>
                </tbody>
            </table>

            <!-- 金额区域 -->
            <table class="amount-table">
                <tr>
                    <td class="amount-label" style="width:18%;">本期对账金额（A）</td>
                    <td style="width:8%;">（小写）：</td>
                    <td class="amount-value" style="width:14%;">&yen;{total_amount:.2f}</td>
                    <td style="width:8%;">（大写）：</td>
                    <td class="amount-cn">{amount_chinese}</td>
                </tr>
                <tr>
                    <td class="amount-label">增值税专用发票税率</td>
                    <td colspan="2" style="text-align:center;">{tax_rate*100:.0f}%</td>
                    <td class="amount-label">本期对账不含税金额</td>
                    <td class="amount-value">&yen;{tax_exempt_amount:.2f}</td>
                </tr>
                <tr>
                    <td class="amount-label">截止上期末累计对账金额(B)</td>
                    <td colspan="2" style="text-align:right; padding-right:8px;">&yen;{prev_total:.2f}</td>
                    <td class="amount-label">截止本期末累计对账金额(C=A+B)</td>
                    <td class="amount-value">&yen;{cumulative_amount:.2f}</td>
                </tr>
            </table>

            <!-- 本期结算说明 -->
            <div style="margin-top:2px; font-size:10px;">
                <span style="font-weight:bold;">本期结算说明：</span>{safe_escape(statement.get('remark'), '')}
            </div>

            <!-- 供方确认 -->
            <div class="supplier-confirm">
                <span class="confirm-title">供货单位确认</span><br>
                本供方承诺：到对账期间截止日，即 {safe_escape(end_year, '')} 年 {safe_escape(end_month, '')} 月 {safe_escape(end_day, '')} 日之前所送物资均已按本对账单进行确认，我方无异议，日后出现本对账单对账截止日期之前的其他送货清单均为无效。<br>
                供方单位（签章）：&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;经办人：&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;&emsp;日期：
            </div>

            <!-- 审批签字表 -->
            <table class="sign-table">
                <thead>
                    <tr>
                        <th style="width:14%;">部门</th>
                        <th style="width:16%;">审批人员</th>
                        <th style="width:46%;">审核内容</th>
                        <th style="width:24%;">审批签字确认</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td rowspan="5" style="text-align:center; font-weight:bold; writing-mode: vertical-rl;">项目部各相关部门意见</td>
                        <td>项目物资</td>
                        <td>材料进场数量、单价与订货数量、单价差异审查</td>
                        <td></td>
                    </tr>
                    <tr>
                        <td>项目预算</td>
                        <td>单价、实际量与预算量差异审查</td>
                        <td></td>
                    </tr>
                    <tr>
                        <td>生产经理/执行经理</td>
                        <td>核对材料质量、供应及时性</td>
                        <td></td>
                    </tr>
                    <tr>
                        <td>项目财务</td>
                        <td>核对原始单据是否符合"四流一致"原则</td>
                        <td></td>
                    </tr>
                    <tr>
                        <td>项目经理</td>
                        <td>复核相应审核内容</td>
                        <td></td>
                    </tr>
                    <tr>
                        <td rowspan="4" style="text-align:center; font-weight:bold; writing-mode: vertical-rl;">公司项目管理中心</td>
                        <td>材料主管/材料员</td>
                        <td>材料型号与合同单价、数量清单符合性审查</td>
                        <td></td>
                    </tr>
                    <tr>
                        <td>成本/预算</td>
                        <td>审单价</td>
                        <td></td>
                    </tr>
                    <tr>
                        <td>项管财务</td>
                        <td>原始单据齐全、合法、合规</td>
                        <td></td>
                    </tr>
                    <tr>
                        <td>部门负责人</td>
                        <td>复核相应审核内容</td>
                        <td></td>
                    </tr>
                </tbody>
            </table>

            <!-- 备注 -->
            <div class="notes">
                <span class="notes-title">备注：</span><br>
                &emsp;&emsp;1、每月20号-25号为本月所供物资的对账日期，相关时间内未来对账的，将顺延到下个月再对账，供应商需提供经需方签收的送货清单及统一格式按时间次序排布的对账单，在对账日期到项目部核对；<br>
                &emsp;&emsp;2、表单作为资金申请的附件；<br>
                &emsp;&emsp;3、对账单及相关送货单、入库单、出库单、发票等原始单据要求至月底26日前提交至项目管理处；<br>
                &emsp;&emsp;4、对账单一式2份，双面打印，不要私自改动模板公式。
            </div>
        </div>
    </body>
    </html>
    """

    response = make_response(html)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response