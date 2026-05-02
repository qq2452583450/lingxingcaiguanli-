"""
询价单蓝图
"""
from flask import Blueprint, request, jsonify, session, make_response
from datetime import datetime
from html import escape
from helpers import amount_to_chinese, get_db, generate_inquiry_no
import sys
sys.path.insert(0, '.')
from helpers.generate_inquiry_no import generate_inquiry_no_by_project

inquiry_bp = Blueprint('inquiries', __name__, url_prefix='/api')


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
    """获取询价单详情（嵌套结构）"""
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

    # 查询新的 items + quotes 嵌套结构
    cursor.execute("""
        SELECT pi.*, m.material_name, m.specification, m.material_code, u.unit_name
        FROM purchase_inquiry_items pi
        LEFT JOIN materials m ON pi.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        WHERE pi.inquiry_id = ?
        ORDER BY pi.id
    """, (inquiry_id,))
    items = []
    for item_row in cursor.fetchall():
        item = dict(item_row)
        item_id = item['id']
        # 查询该item下的所有报价
        cursor.execute("""
            SELECT pq.*, s.supplier_name
            FROM purchase_inquiry_quotes pq
            LEFT JOIN suppliers s ON pq.supplier_id = s.id
            WHERE pq.item_id = ?
            ORDER BY pq.id
        """, (item_id,))
        item['quotes'] = [dict(q) for q in cursor.fetchall()]
        items.append(item)

    # 如果没有新结构数据，尝试兼容旧结构（purchase_inquiry_details）
    if not items:
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
        return jsonify({'success': True, 'data': inquiry, 'details': details, 'legacy': True})

    conn.close()
    return jsonify({'success': True, 'data': inquiry, 'items': items})


@inquiry_bp.route('/purchase-inquiries', methods=['POST'])
def create_inquiry():
    """创建询价单（支持新的 items/quotes 嵌套结构）"""
    import json as json_module

    print("=== create_inquiry called ===")
    print("Raw request.data:", request.data)

    # 手动解析 JSON
    try:
        data = json_module.loads(request.data)
        print("Manually parsed data:", data)
    except Exception as e:
        print("JSON parse error:", e)
        return jsonify({'success': False, 'message': 'JSON解析失败: ' + str(e)})

    if data is None:
        return jsonify({'success': False, 'message': '请求数据为空'})

    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()

    # 详细检查 items 结构
    print("All keys in data:", list(data.keys()))

    # 判断数据格式：items 字段存在则走新结构，否则走旧结构兼容
    has_items_key = 'items' in data
    items_data = data.get('items', []) if has_items_key else []
    print("has_items_key:", has_items_key, "items_data:", items_data)

    # 如果 items 字段不存在，尝试 details（旧结构兼容）
    if not has_items_key:
        items_data = data.get('details', [])
        print("items_data from get('details', []):", items_data)

    is_new_format = has_items_key and isinstance(items_data, list)
    print("is_new_format:", is_new_format)

    if is_new_format:
        # 新结构：items 格式
        if len(items_data) == 0:
            return jsonify({'success': False, 'message': '请添加询价材料（明细不能为空）'})

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 计算总金额
        total_amount = 0
        for item in items_data:
            for quote in item.get('quotes', []):
                tax_price = float(quote.get('tax_price', 0) or 0)
                quantity = float(item.get('quantity', 1) or 1)
                total_amount += tax_price * quantity

        # 判断是否低于库内价
        is_below = 0
        for item in items_data:
            library_price = float(item.get('library_price', 0) or 0)
            for quote in item.get('quotes', []):
                tax_price = float(quote.get('tax_price', 0) or 0)
                if library_price > 0 and tax_price < library_price:
                    is_below = 1
                    break
            if is_below:
                break

        # 写入主表
        inquiry_no = None
        inquiry_id = None
        
        # 检查表结构，确保 project_id 列存在
        cursor.execute("PRAGMA table_info(purchase_inquiries)")
        columns = [row[1] for row in cursor.fetchall()]
        has_project_id = 'project_id' in columns
        
        if not has_project_id:
            print("警告: purchase_inquiries 表缺少 project_id 列，正在添加...")
            try:
                cursor.execute("ALTER TABLE purchase_inquiries ADD COLUMN project_id INTEGER")
                has_project_id = True
            except Exception as e:
                print(f"添加 project_id 列失败: {e}")
        
        for attempt in range(5):
            try:
                # 根据项目ID生成询价单号
                project_id = data.get('project_id')
                inquiry_date = data.get('inquiry_date', now[:10])
                if project_id:
                    inquiry_no = generate_inquiry_no_by_project(project_id, inquiry_date)
                else:
                    inquiry_no = generate_inquiry_no()

                # 根据表结构动态构建INSERT语句
                if has_project_id:
                    cursor.execute("""
                        INSERT INTO purchase_inquiries (
                            inquiry_no, inquiry_date, applicant_id, project_id, total_amount,
                            is_below_library_price, approval_status, create_time, remark
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        inquiry_no, inquiry_date,
                        user['id'], project_id, total_amount, is_below, '待审批', now, data.get('remark', '')
                    ))
                else:
                    cursor.execute("""
                        INSERT INTO purchase_inquiries (
                            inquiry_no, inquiry_date, applicant_id, total_amount,
                            is_below_library_price, approval_status, create_time, remark
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        inquiry_no, inquiry_date,
                        user['id'], total_amount, is_below, '待审批', now, data.get('remark', '')
                    ))
                inquiry_id = cursor.lastrowid
                break
            except Exception as insert_err:
                err_str = str(insert_err)
                if 'UNIQUE constraint failed' in err_str and attempt < 4:
                    print(f"inquiry_no冲突，第{attempt + 1}次重试")
                    conn.rollback()
                    continue
                conn.close()
                return jsonify({'success': False, 'message': f'创建失败: {err_str}'})

        if inquiry_id is None:
            conn.close()
            return jsonify({'success': False, 'message': '无法生成唯一单号，请稍后重试'})

        # 写入 items + quotes
        try:
            for item in items_data:
                material_id = item.get('material_id')
                quantity = float(item.get('quantity', 1) or 1)
                library_price = float(item.get('library_price', 0) or 0)
                selected_quote_id = item.get('selected_quote_id')
                tax_rate = float(item.get('tax_rate', 0.01) or 0.01)

                cursor.execute("""
                    INSERT INTO purchase_inquiry_items (
                        inquiry_id, material_id, quantity, library_price,
                        selected_quote_id, tax_rate, create_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    inquiry_id,
                    material_id if material_id else None,
                    quantity, library_price,
                    selected_quote_id, tax_rate, now
                ))
                item_id = cursor.lastrowid

                # 写入该item的所有报价
                quotes = item.get('quotes', [])
                valid_quotes = [q for q in quotes if q.get('supplier_id') and q.get('tax_price', 0) > 0]

                if valid_quotes:
                    # 计算最低价
                    prices_with_idx = [(float(q['tax_price']) * quantity, i) for i, q in enumerate(valid_quotes)]
                    lowest_idx = min(prices_with_idx, key=lambda x: x[0])[1] if prices_with_idx else -1

                    for i, quote in enumerate(valid_quotes):
                        tax_price = float(quote.get('tax_price', 0) or 0)
                        tax_exempt_price = float(quote.get('tax_exempt_price', 0) or 0)
                        tax_rate = float(quote.get('tax_rate', 0.13) or 0.13)
                        total = tax_price * quantity

                        # 自动计算不含税单价（如果未提供）
                        if tax_exempt_price == 0 and tax_price > 0:
                            tax_exempt_price = round(tax_price / (1 + tax_rate), 2)

                        cursor.execute("""
                            INSERT INTO purchase_inquiry_quotes (
                                item_id, supplier_id, tax_price, tax_exempt_price,
                                tax_rate, total_amount, is_lowest, is_selected, create_time
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            item_id,
                            quote.get('supplier_id'),
                            tax_price, tax_exempt_price,
                            tax_rate, total,
                            1 if i == lowest_idx else 0,
                            1 if selected_quote_id and quote.get('supplier_id') == selected_quote_id else 0,
                            now
                        ))

            # 记录提交审批操作
            cursor.execute("""
                INSERT INTO approval_records (order_type, order_id, approver_id, approver_name, result, remark, approval_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ('purchase_inquiry', inquiry_id, user['id'], user['real_name'], '提交审批', '', now))

            conn.commit()
            conn.close()
            return jsonify({'success': True, 'inquiry_no': inquiry_no, 'id': inquiry_id})

        except Exception as e:
            print("Error:", str(e))
            import traceback
            traceback.print_exc()
            conn.rollback()
            conn.close()
            return jsonify({'success': False, 'message': str(e)})

    else:
        # 旧结构兼容：直接使用 details
        details = data.get('details', [])
        if not isinstance(details, list):
            return jsonify({'success': False, 'message': '明细数据格式错误：应该为数组'})
        if len(details) == 0:
            return jsonify({'success': False, 'message': '明细数据不能为空'})

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        total_amount = sum(float(d.get('this_price', 0) or 0) * float(d.get('quantity', 1) or 1) for d in details)
        is_below = 1 if any(float(d.get('this_price', 0) or 0) < float(d.get('library_price', 0) or 0) for d in details) else 0

        inquiry_no = None
        inquiry_id = None
        
        # 检查表结构，确保 project_id 列存在
        cursor.execute("PRAGMA table_info(purchase_inquiries)")
        columns = [row[1] for row in cursor.fetchall()]
        has_project_id = 'project_id' in columns
        
        if not has_project_id:
            print("警告: purchase_inquiries 表缺少 project_id 列，正在添加...")
            try:
                cursor.execute("ALTER TABLE purchase_inquiries ADD COLUMN project_id INTEGER")
                has_project_id = True
            except Exception as e:
                print(f"添加 project_id 列失败: {e}")

        for attempt in range(5):
            try:
                # 根据项目ID生成询价单号
                project_id = data.get('project_id')
                inquiry_date = data.get('inquiry_date', now[:10])
                if project_id:
                    inquiry_no = generate_inquiry_no_by_project(project_id, inquiry_date)
                else:
                    inquiry_no = generate_inquiry_no()

                # 根据表结构动态构建INSERT语句
                if has_project_id:
                    cursor.execute("""
                        INSERT INTO purchase_inquiries (
                            inquiry_no, inquiry_date, applicant_id, project_id, total_amount,
                            is_below_library_price, approval_status, create_time, remark
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        inquiry_no, inquiry_date,
                        user['id'], project_id, total_amount, is_below, '待审批', now, data.get('remark', '')
                    ))
                else:
                    cursor.execute("""
                        INSERT INTO purchase_inquiries (
                            inquiry_no, inquiry_date, applicant_id, total_amount,
                            is_below_library_price, approval_status, create_time, remark
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        inquiry_no, inquiry_date,
                        user['id'], total_amount, is_below, '待审批', now, data.get('remark', '')
                    ))
                inquiry_id = cursor.lastrowid
                break
            except Exception as insert_err:
                err_str = str(insert_err)
                if 'UNIQUE constraint failed' in err_str and attempt < 4:
                    print(f"inquiry_no冲突，第{attempt + 1}次重试")
                    conn.rollback()
                    continue
                conn.close()
                return jsonify({'success': False, 'message': f'创建失败: {err_str}'})

        if inquiry_id is None:
            conn.close()
            return jsonify({'success': False, 'message': '无法生成唯一单号，请稍后重试'})

        try:
            for d in details:
                material_id = d.get('material_id')
                supplier_id = d.get('supplier_id')
                this_price = float(d.get('this_price', 0) or 0)
                library_price = float(d.get('library_price', 0) or 0)
                quantity = int(d.get('quantity', 1) or 1)
                tax_rate = float(d.get('tax_rate', 0.13) or 0.13)

                is_lowest = 1 if this_price <= library_price else 0
                price_diff = this_price - library_price

                cursor.execute("""
                    INSERT INTO purchase_inquiry_details (
                        inquiry_id, material_id, supplier_id, this_price,
                        library_price, is_lowest, price_diff, quantity, tax_rate
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    inquiry_id,
                    material_id if material_id else None,
                    supplier_id if supplier_id else None,
                    this_price, library_price,
                    is_lowest, price_diff, quantity, tax_rate
                ))

            # 记录提交审批操作
            cursor.execute("""
                INSERT INTO approval_records (order_type, order_id, approver_id, approver_name, result, remark, approval_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ('purchase_inquiry', inquiry_id, user['id'], user['real_name'], '提交审批', '', now))

            conn.commit()
            conn.close()
            return jsonify({'success': True, 'inquiry_no': inquiry_no, 'id': inquiry_id})

        except Exception as e:
            print("Error:", str(e))
            import traceback
            traceback.print_exc()
            conn.rollback()
            conn.close()
            return jsonify({'success': False, 'message': str(e)})


@inquiry_bp.route('/purchase-inquiries/<int:inquiry_id>', methods=['DELETE'])
def delete_inquiry(inquiry_id):
    """删除询价单"""
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    if user.get('role_name') != '系统管理员':
        return jsonify({'success': False, 'message': '仅管理员可删除询价单'})

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM purchase_inquiry_items WHERE inquiry_id = ?", (inquiry_id,))
    cursor.execute("DELETE FROM purchase_inquiry_quotes WHERE item_id IN (SELECT id FROM purchase_inquiry_items WHERE inquiry_id = ?)", (inquiry_id,))
    cursor.execute("DELETE FROM purchase_inquiries WHERE id = ?", (inquiry_id,))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': '删除成功'})


@inquiry_bp.route('/purchase-inquiries/<int:inquiry_id>/approve', methods=['POST'])
def approve_inquiry(inquiry_id):
    """审批询价单（支持新的 items/quotes 结构）"""
    data = request.json
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'message': '未登录'})

    # 权限校验：只有系统管理员和材料员可以审批
    conn_check = get_db()
    cursor_check = conn_check.cursor()
    cursor_check.execute("SELECT r.role_name FROM users u LEFT JOIN roles r ON u.role_id = r.id WHERE u.id = ?", (user['id'],))
    role_row = cursor_check.fetchone()
    conn_check.close()
    role_name = dict(role_row)['role_name'] if role_row else None
    if role_name not in ('系统管理员', '材料员'):
        return jsonify({'success': False, 'message': '您没有审批权限，仅系统管理员或材料员可审批'})

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
        updated_rows = cursor.rowcount
    elif action == 'material_clerk':
        cursor.execute("""
            UPDATE purchase_inquiries
            SET approval_status = '材料员已审', approver_id = ?, approve_time = ?, approval_remark = ?
            WHERE id = ? AND approval_status = '待审批'
        """, (user['id'], now, remark, inquiry_id))
        updated_rows = cursor.rowcount
    elif action == 'manager':
        # 主管审批：待审批 或 材料员已审 都可直接通过
        cursor.execute("""
            UPDATE purchase_inquiries
            SET approval_status = '已同意', approver_id = ?, approve_time = ?, approval_remark = ?
            WHERE id = ? AND approval_status IN ('待审批', '材料员已审')
        """, (user['id'], now, remark, inquiry_id))
        updated_rows = cursor.rowcount

        # 尝试新的 items 结构
        cursor.execute("SELECT * FROM purchase_inquiry_items WHERE inquiry_id = ?", (inquiry_id,))
        items = cursor.fetchall()

        # 获取询价单所属项目的信息（用于生成新编号）
        cursor.execute("SELECT * FROM purchase_inquiries WHERE id = ?", (inquiry_id,))
        inq = dict(cursor.fetchone())
        inquiry_project_id = inq.get('project_id')

        # 获取询价单所在项目的前缀（用于判断是否需要生成新编号）
        cursor.execute("SELECT project_code FROM projects WHERE id = ?", (inquiry_project_id,))
        proj_row = cursor.fetchone()
        inquiry_project_code = proj_row[0] if proj_row else ''
        inquiry_prefix = inquiry_project_code[:2].upper() if inquiry_project_code else ''

        def generate_new_material_code(cursor, project_code):
            """根据项目编码生成新的材料编号"""
            prefix = project_code[:2].upper() + 'LX'
            cursor.execute("SELECT material_code FROM materials WHERE material_code LIKE ? ORDER BY id DESC LIMIT 1",
                           (prefix + '%',))
            last_row = cursor.fetchone()
            if last_row:
                last_code = last_row[0]
                try:
                    num = int(last_code[len(prefix):])
                    next_num = num + 1
                except ValueError:
                    next_num = 1
            else:
                next_num = 1
            return prefix + str(next_num).zfill(5)

        if items:
            for item in items:
                item_dict = dict(item)
                material_id = item_dict['material_id']

                # 获取当前材料的编码前缀
                cursor.execute("SELECT material_code FROM materials WHERE id = ?", (material_id,))
                mat_row = cursor.fetchone()
                material_code = mat_row[0] if mat_row else ''
                material_prefix = material_code[:2].upper() if material_code and len(material_code) >= 2 else ''

                # 判断是否需要生成新编号
                need_new_code = (material_prefix != inquiry_prefix) and inquiry_prefix

                if need_new_code:
                    # 生成新编号
                    new_code = generate_new_material_code(cursor, inquiry_project_code)
                    print(f"材料 {material_id} 编号变更: {material_code} -> {new_code}")

                # 查找选定的报价（is_selected=1）
                cursor.execute("""
                    SELECT * FROM purchase_inquiry_quotes
                    WHERE item_id = ? AND is_selected = 1 LIMIT 1
                """, (item_dict['id'],))
                selected_quote = cursor.fetchone()

                if selected_quote:
                    quote_tax_rate = float(selected_quote.get('tax_rate', 0.01) or 0.01)
                    # 根据选定的报价更新材料价格
                    if need_new_code:
                        # 新编号 + 完整更新
                        cursor.execute("""
                            UPDATE materials SET material_code = ?, tax_price = ?, tax_exempt_price = ?,
                            default_supplier_id = ?, detail_spec = ?, is_national_standard = ?, brand = ?, tax_rate = ?
                            WHERE id = ?
                        """, (
                            new_code,
                            selected_quote['tax_price'],
                            selected_quote['tax_exempt_price'],
                            selected_quote['supplier_id'],
                            escape(data.get('detail_spec', '')),
                            data.get('is_national_standard', 0),
                            escape(data.get('brand', '')),
                            quote_tax_rate,
                            material_id
                        ))
                    else:
                        # 同项目只更新价格
                        cursor.execute(
                            "UPDATE materials SET tax_price = ?, tax_exempt_price = ?, default_supplier_id = ?, tax_rate = ? WHERE id = ?",
                            (selected_quote['tax_price'], selected_quote['tax_exempt_price'], selected_quote['supplier_id'], quote_tax_rate, material_id)
                        )
                else:
                    # 如果没有选定，使用最低价报价
                    cursor.execute("""
                        SELECT * FROM purchase_inquiry_quotes
                        WHERE item_id = ? AND is_lowest = 1 LIMIT 1
                    """, (item_dict['id'],))
                    lowest_quote = cursor.fetchone()
                    if lowest_quote:
                        quote_tax_rate = float(lowest_quote.get('tax_rate', 0.01) or 0.01)
                        if need_new_code:
                            cursor.execute("""
                                UPDATE materials SET material_code = ?, tax_price = ?, tax_exempt_price = ?,
                                default_supplier_id = ?, detail_spec = ?, is_national_standard = ?, brand = ?, tax_rate = ?
                                WHERE id = ?
                            """, (
                                new_code,
                                lowest_quote['tax_price'],
                                lowest_quote['tax_exempt_price'],
                                lowest_quote['supplier_id'],
                                escape(data.get('detail_spec', '')),
                                data.get('is_national_standard', 0),
                                escape(data.get('brand', '')),
                                quote_tax_rate,
                                material_id
                            ))
                        else:
                            cursor.execute(
                                "UPDATE materials SET tax_price = ?, tax_exempt_price = ?, default_supplier_id = ?, tax_rate = ? WHERE id = ?",
                                (lowest_quote['tax_price'], lowest_quote['tax_exempt_price'], lowest_quote['supplier_id'], quote_tax_rate, material_id)
                            )
        else:
            # 兼容旧结构：purchase_inquiry_details
            cursor.execute("SELECT * FROM purchase_inquiry_details WHERE inquiry_id = ?", (inquiry_id,))
            for d in cursor.fetchall():
                material_id = d['material_id']
                tax_price = d['this_price']
                tax_exempt = round(tax_price / 1.01, 2)
                supplier_id = d['supplier_id']

                # 获取当前材料的编码前缀
                cursor.execute("SELECT material_code FROM materials WHERE id = ?", (material_id,))
                mat_row = cursor.fetchone()
                material_code = mat_row[0] if mat_row else ''
                material_prefix = material_code[:2].upper() if material_code and len(material_code) >= 2 else ''

                # 判断是否需要生成新编号
                need_new_code = (material_prefix != inquiry_prefix) and inquiry_prefix

                if need_new_code:
                    # 生成新编号
                    new_code = generate_new_material_code(cursor, inquiry_project_code)
                    print(f"材料 {material_id} 编号变更: {material_code} -> {new_code}")
                    if supplier_id:
                        cursor.execute("""
                            UPDATE materials SET material_code = ?, tax_price = ?, tax_exempt_price = ?,
                            default_supplier_id = ?, detail_spec = ?, is_national_standard = ?, brand = ?
                            WHERE id = ?
                        """, (new_code, tax_price, tax_exempt, supplier_id, '', 0, '', material_id))
                    else:
                        cursor.execute("""
                            UPDATE materials SET material_code = ?, tax_price = ?, tax_exempt_price = ?,
                            detail_spec = ?, is_national_standard = ?, brand = ?
                            WHERE id = ?
                        """, (new_code, tax_price, tax_exempt, '', 0, '', material_id))
                else:
                    # 同项目只更新价格
                    if supplier_id:
                        cursor.execute(
                            "UPDATE materials SET tax_price = ?, tax_exempt_price = ?, default_supplier_id = ? WHERE id = ?",
                            (tax_price, tax_exempt, supplier_id, material_id)
                        )
                    else:
                        cursor.execute(
                            "UPDATE materials SET tax_price = ?, tax_exempt_price = ? WHERE id = ?",
                            (tax_price, tax_exempt, material_id)
                        )

        cursor.execute("UPDATE purchase_inquiries SET library_price_updated = 1 WHERE id = ?", (inquiry_id,))

        # ===== 审批通过后自动入库 =====
        # 生成入库单号
        today_str = datetime.now().strftime('%Y%m%d')
        cursor.execute("SELECT COUNT(*) FROM stock_in_orders WHERE order_no LIKE ?", (f'JH-{today_str}%',))
        stk_count = cursor.fetchone()[0] + 1
        stock_in_no = f'JH-{today_str}-{str(stk_count).zfill(3)}'

        # 获取询价单信息
        cursor.execute("SELECT * FROM purchase_inquiries WHERE id = ?", (inquiry_id,))
        inq = dict(cursor.fetchone())

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 创建入库主单
        cursor.execute("""
            INSERT INTO stock_in_orders (
                order_no, source_type, related_order_no, supplier_id,
                warehouse_id, project_id, operator_id, in_time, status, create_time, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            stock_in_no, '采购入库', inq.get('inquiry_no', ''), None,
            1, inq.get('project_id'), user['id'], now_str, '已入库', now_str,
            f'询价单{inq.get("inquiry_no", "")}审批通过自动入库'
        ))
        stock_in_id = cursor.lastrowid

        # 遍历选定报价，创建入库明细并更新库存
        if items:
            for item in items:
                item_dict = dict(item)
                material_id = item_dict['material_id']
                quantity = item_dict.get('quantity', 1)

                unit_price = 0
                supplier_id = None

                # 优先查找 is_selected=1 的报价（前端选定的拟定供应商）
                cursor.execute("""
                    SELECT * FROM purchase_inquiry_quotes
                    WHERE item_id = ? AND is_selected = 1 LIMIT 1
                """, (item_dict['id'],))
                q = cursor.fetchone()

                # 如果没有 is_selected 的，退而查找 is_lowest=1 的最低价报价
                if not q:
                    cursor.execute("""
                        SELECT * FROM purchase_inquiry_quotes
                        WHERE item_id = ? AND is_lowest = 1 LIMIT 1
                    """, (item_dict['id'],))
                    q = cursor.fetchone()

                # 最后兜底：取该 item 下任意一条有效报价
                if not q:
                    cursor.execute("""
                        SELECT * FROM purchase_inquiry_quotes
                        WHERE item_id = ? AND tax_price > 0 LIMIT 1
                    """, (item_dict['id'],))
                    q = cursor.fetchone()

                if q:
                    unit_price = q['tax_price'] or 0
                    supplier_id = q['supplier_id']

                if unit_price > 0 and quantity > 0:
                    amount = unit_price * quantity
                    # 入库明细
                    cursor.execute("""
                        INSERT INTO stock_in_details (order_id, material_id, quantity, unit_price, amount)
                        VALUES (?, ?, ?, ?, ?)
                    """, (stock_in_id, material_id, quantity, unit_price, amount))

                    # 更新库存
                    cursor.execute("""
                        SELECT id FROM inventory WHERE material_id = ? AND warehouse_id = ?
                    """, (material_id, 1))
                    existing_inv = cursor.fetchone()
                    if existing_inv:
                        cursor.execute("""
                            UPDATE inventory SET quantity = quantity + ?, unit_price = ?, update_time = ?
                            WHERE material_id = ? AND warehouse_id = ?
                        """, (quantity, unit_price, now_str, material_id, 1))
                    else:
                        cursor.execute("""
                            INSERT INTO inventory (material_id, warehouse_id, quantity, unit_price, update_time)
                            VALUES (?, ?, ?, ?, ?)
                        """, (material_id, 1, quantity, unit_price, now_str))

                    # 更新入库单的供应商（用第一个有供应商的报价）
                    if supplier_id:
                        cursor.execute("UPDATE stock_in_orders SET supplier_id = ? WHERE id = ? AND supplier_id IS NULL", (supplier_id, stock_in_id))
        else:
            # 兼容旧结构
            cursor.execute("SELECT * FROM purchase_inquiry_details WHERE inquiry_id = ?", (inquiry_id,))
            for d in cursor.fetchall():
                d_dict = dict(d)
                material_id = d_dict['material_id']
                quantity = d_dict.get('quantity', 1)
                unit_price = d_dict.get('this_price', 0)
                supplier_id = d_dict.get('supplier_id')

                if unit_price > 0 and quantity > 0:
                    amount = unit_price * quantity
                    cursor.execute("""
                        INSERT INTO stock_in_details (order_id, material_id, quantity, unit_price, amount)
                        VALUES (?, ?, ?, ?, ?)
                    """, (stock_in_id, material_id, quantity, unit_price, amount))

                    cursor.execute("""
                        SELECT id FROM inventory WHERE material_id = ? AND warehouse_id = ?
                    """, (material_id, 1))
                    existing_inv = cursor.fetchone()
                    if existing_inv:
                        cursor.execute("""
                            UPDATE inventory SET quantity = quantity + ?, unit_price = ?, update_time = ?
                            WHERE material_id = ? AND warehouse_id = ?
                        """, (quantity, unit_price, now_str, material_id, 1))
                    else:
                        cursor.execute("""
                            INSERT INTO inventory (material_id, warehouse_id, quantity, unit_price, update_time)
                            VALUES (?, ?, ?, ?, ?)
                        """, (material_id, 1, quantity, unit_price, now_str))

                    if supplier_id:
                        cursor.execute("UPDATE stock_in_orders SET supplier_id = ? WHERE id = ? AND supplier_id IS NULL", (supplier_id, stock_in_id))
        # ===== 自动入库结束 =====
    else:
        conn.close()
        return jsonify({'success': False, 'message': '无效的操作'})

    if updated_rows == 0:
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
    """打印询价单审批签字单（支持新的 items/quotes 嵌套结构）"""
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

    # 尝试新的 items + quotes 结构
    cursor.execute("""
        SELECT pi.*, m.material_name, m.specification, m.material_code, u.unit_name
        FROM purchase_inquiry_items pi
        LEFT JOIN materials m ON pi.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        WHERE pi.inquiry_id = ?
        ORDER BY pi.id
    """, (inquiry_id,))
    items = []
    for item_row in cursor.fetchall():
        item = dict(item_row)
        item_id = item['id']
        cursor.execute("""
            SELECT pq.*, s.supplier_name
            FROM purchase_inquiry_quotes pq
            LEFT JOIN suppliers s ON pq.supplier_id = s.id
            WHERE pq.item_id = ?
            ORDER BY pq.id
        """, (item_id,))
        item['quotes'] = [dict(q) for q in cursor.fetchall()]
        items.append(item)

    # 如果没有新结构数据，使用旧结构
    if not items:
        cursor.execute("""
            SELECT pd.*, m.material_name, m.specification, m.material_code, u.unit_name, s.supplier_name
            FROM purchase_inquiry_details pd
            LEFT JOIN materials m ON pd.material_id = m.id
            LEFT JOIN units u ON m.unit_id = u.id
            LEFT JOIN suppliers s ON pd.supplier_id = s.id
            WHERE pd.inquiry_id = ?
        """, (inquiry_id,))
        details = [dict(row) for row in cursor.fetchall()]
    else:
        details = None

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
            .signatures {{ display: flex; justify-content: space-between; margin-top: 40px; }}
            .signature-item {{ text-align: center; width: 20%; }}
            .signature-line {{ border-top: 1px solid #333; margin-top: 40px; padding-top: 5px; }}
            .amount-chinese {{ font-size: 18px; font-weight: bold; color: #c0392b; margin-top: 10px; }}
            .item-card {{ border: 1px solid #ddd; margin-bottom: 15px; border-radius: 4px; }}
            .item-header {{ background: #f5f5f5; padding: 8px 10px; border-bottom: 1px solid #ddd; font-weight: bold; }}
            .quote-row {{ display: flex; padding: 6px 10px; border-bottom: 1px solid #eee; }}
            .quote-row:last-child {{ border-bottom: none; }}
            .quote-row.lowest {{ background: #f0fff4; }}
            .quote-supplier {{ width: 150px; }}
            .quote-price {{ width: 100px; text-align: right; }}
            .quote-amount {{ width: 100px; text-align: right; font-weight: bold; }}
            .quote-selected {{ width: 60px; color: #27ae60; font-weight: bold; }}
            .lowest-tag {{ color: #27ae60; font-size: 11px; }}
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
"""

    if items:
        # 新结构：嵌套展示，材料名+规格相同行合并（rowspan）
        html += """<table>
                <thead>
                    <tr>
                        <th>名称</th>
                        <th>规格</th>
                        <th>单位</th>
                        <th>数量</th>
                        <th>库内价</th>
                        <th>供应商</th>
                        <th>含税单价</th>
                        <th>报价金额</th>
                        <th>最低价</th>
                        <th>拟定</th>
                    </tr>
                </thead>
                <tbody>
"""
        for item in items:
            material_name = item.get('material_name', '')
            specification = item.get('specification', '-')
            unit_name = item.get('unit_name', '-')
            quantity = item.get('quantity', 1)
            library_price = item.get('library_price', 0)
            quotes = item.get('quotes', [])

            if not quotes:
                # 无报价时单行显示
                html += f"""
                    <tr>
                        <td style="font-weight:500;">{escape(material_name)}</td>
                        <td>{escape(specification)}</td>
                        <td>{escape(unit_name)}</td>
                        <td>{quantity}</td>
                        <td>¥{library_price:.2f}</td>
                        <td>-</td>
                        <td>-</td>
                        <td>-</td>
                        <td></td>
                        <td></td>
                    </tr>
"""
            else:
                rowspan = f' rowspan="{len(quotes)}"' if len(quotes) > 1 else ''
                for qi, quote in enumerate(quotes):
                    html += "<tr>"
                    if qi == 0:
                        html += f'<td{rowspan} style="font-weight:500;vertical-align:middle;">{escape(material_name)}</td>'
                        html += f'<td{rowspan} style="vertical-align:middle;">{escape(specification)}</td>'
                        html += f'<td{rowspan} style="vertical-align:middle;">{escape(unit_name)}</td>'
                        html += f'<td{rowspan} style="vertical-align:middle;">{quantity}</td>'
                        html += f'<td{rowspan} style="vertical-align:middle;">¥{library_price:.2f}</td>'
                    html += f'<td>{escape(quote.get("supplier_name", "-"))}</td>'
                    html += f'<td>¥{quote.get("tax_price", 0):.2f}</td>'
                    html += f'<td>¥{quote.get("total_amount", 0):.2f}</td>'
                    lowest_html = '<span class="lowest-tag">最低</span>' if quote.get('is_lowest') == 1 else ''
                    html += f'<td>{lowest_html}</td>'
                    selected_html = '✓' if quote.get('is_selected') == 1 else ''
                    html += f'<td>{selected_html}</td>'
                    html += "</tr>\n"
        html += """                </tbody>
            </table>
"""
    else:
        # 旧结构：扁平展示，材料名+规格相同行合并（rowspan）
        html += """<table>
                <thead>
                    <tr>
                        <th>名称</th>
                        <th>规格</th>
                        <th>单位</th>
                        <th>库内价</th>
                        <th>供应商</th>
                        <th>本次报价</th>
                        <th>差额</th>
                    </tr>
                </thead>
                <tbody>
"""
        # 按材料名+规格分组
        from itertools import groupby
        def detail_group_key(d):
            return (d.get('material_name', ''), d.get('specification', '-'))
        sorted_details = sorted(details, key=detail_group_key)
        for key, group_iter in groupby(sorted_details, key=detail_group_key):
            group_rows = list(group_iter)
            rowspan = f' rowspan="{len(group_rows)}"' if len(group_rows) > 1 else ''
            for gi, d in enumerate(group_rows):
                html += "<tr>"
                if gi == 0:
                    html += f'<td{rowspan} style="font-weight:500;vertical-align:middle;">{escape(key[0])}</td>'
                    html += f'<td{rowspan} style="vertical-align:middle;">{escape(key[1])}</td>'
                    html += f'<td{rowspan} style="vertical-align:middle;">{escape(d.get("unit_name", "-"))}</td>'
                    html += f'<td{rowspan} style="vertical-align:middle;">¥{d.get("library_price", 0):.2f}</td>'
                html += f'<td>{escape(d.get("supplier_name", "-"))}</td>'
                html += f'<td>¥{d.get("this_price", 0):.2f}</td>'
                diff_color = '#e74c3c' if d.get('price_diff', 0) < 0 else '#27ae60'
                html += f'<td style="color:{diff_color}">¥{d.get("price_diff", 0):.2f}</td>'
                html += "</tr>\n"
        html += """                </tbody>
            </table>
"""

    html += f"""<div style="text-align: right; margin: 15px 0;">
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
        {'level': '部门主管', 'matches': ['主管同意', '主管已审']},
    ]

    for level_info in approval_levels:
        found = next((r for r in approval_records if any(m in r.get('result', '') for m in level_info['matches'])), None)
        if found:
            html += f"""
                        <tr>
                            <td>{level_info['level']}</td>
                            <td>{escape(found.get('approver_name', '-'))}</td>
                            <td style="color: #27ae60;">{escape(found.get('result', '-'))}</td>
                            <td>{escape(found.get('remark') or '-')}</td>
                            <td>{escape(found.get('approval_time', '-'))}</td>
                        </tr>
"""
        else:
            html += f"""
                        <tr>
                            <td>{level_info['level']}</td>
                            <td colspan="4" style="color: #f39c12; font-style: italic;">待审批</td>
                        </tr>
"""

    html += """                    </tbody>
                </table>
            </div>

            <div style="margin-top: 30px; font-size: 12px; color: #666;">
                <strong>备注：</strong>""" + escape(inquiry.get('remark') or '无') + """
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
                打印时间：""" + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """
            </div>
        </div>
    </body>
    </html>
    """

    response = make_response(html)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response
