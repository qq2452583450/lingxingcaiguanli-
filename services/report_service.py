"""Read-only reports built from business records, shared by the UI and export."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP


REPORT_NAMES = {
    'purchase': '采购询比价分析', 'stock_in': '入库明细', 'stock_out': '出库明细',
    'inventory': '当前仓库库存', 'base_inventory': '当前基地库存',
    'transfers': '基地调拨统计', 'cash': '备用金支出统计',
}


def number(value):
    return Decimal(str(value or 0))


def money(value):
    return float(number(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def filters_from_args(args):
    today = date.today()
    result = {key: (args.get(key) or '').strip() for key in
              ('project_id', 'supplier_id', 'keyword', 'unit')}
    result['kind'] = args.get('kind', 'purchase')
    if result['kind'] not in REPORT_NAMES:
        raise ValueError('请选择有效的报表类型')
    for key, fallback in [('start_date', today.replace(day=1)), ('end_date', today)]:
        text = args.get(key) or fallback.isoformat()
        try:
            parsed = date.fromisoformat(text)
        except ValueError:
            raise ValueError('日期格式应为 YYYY-MM-DD')
        result[key] = parsed.isoformat()
    if result['start_date'] > result['end_date']:
        raise ValueError('开始日期不能晚于结束日期')
    if result['end_date'] == '9999-12-31':
        raise ValueError('结束日期超出支持范围')
    for key in ('project_id', 'supplier_id'):
        if result[key]:
            try:
                result[key] = int(result[key])
            except ValueError:
                raise ValueError('项目或供应商参数无效')
            if result[key] < 1:
                raise ValueError('项目或供应商参数无效')
    return result


def project_scope(conn, user):
    """Read the current role and project grants, never trust a client role."""
    row = conn.execute('''SELECT r.role_name FROM users u JOIN roles r ON r.id=u.role_id
                          WHERE u.id=? AND u.is_active=1''', (user['id'],)).fetchone()
    if not row or row['role_name'] not in ('系统管理员', '材料审批负责人', '材料员', '基地负责人'):
        raise PermissionError('当前账号无权查看内部报表')
    if row['role_name'] == '系统管理员':
        return None
    return [r[0] for r in conn.execute('SELECT project_id FROM user_projects WHERE user_id=?', (user['id'],))]


def where_project(expression, f, scope, params):
    if f['project_id']:
        if scope is not None and f['project_id'] not in scope:
            raise PermissionError('无权查看所选项目')
        params.append(f['project_id'])
        return expression + ' = ?'
    if scope is not None:
        params.extend(scope)
        return expression + ' IN (' + ','.join('?' for _ in scope) + ')' if scope else '0=1'
    return '1=1'


def dated(expression, f, params):
    params.extend([f['start_date'], (date.fromisoformat(f['end_date']) + timedelta(days=1)).isoformat()])
    return f'{expression} >= ? AND {expression} < ?'


def table(key, title, columns, rows):
    return {'key': key, 'title': title,
            'columns': [{'key': c[0], 'label': c[1], 'type': c[2] if len(c) > 2 else 'text'} for c in columns],
            'rows': rows}


def matches(row, f):
    if f['supplier_id'] and row.get('supplier_id') != f['supplier_id']:
        return False
    if f['unit'] and row.get('unit_name') != f['unit']:
        return False
    return not f['keyword'] or f['keyword'].casefold() in ' '.join(str(row.get(k) or '') for k in
                ('material_name', 'material_code', 'specification', 'detail_spec')).casefold()


def groups(rows, keys):
    result = {}
    for row in rows:
        key = tuple(row.get(k) for k in keys)
        if key not in result:
            result[key] = {**{k: row.get(k) for k in keys}, 'goods': Decimal(0),
                           'freight': Decimal(0), 'quantity': Decimal(0), 'orders': set()}
        group = result[key]
        for field in ('goods', 'freight', 'quantity'):
            group[field] += number(row.get(field))
        group['orders'].add(row['order_id'])
    output = []
    for group in result.values():
        group['count'] = len(group.pop('orders'))
        group['amount'] = money(group['goods'] + group['freight'])
        group['goods'], group['freight'] = money(group['goods']), money(group['freight'])
        group['quantity'] = float(group['quantity'])
        output.append(group)
    return sorted(output, key=lambda r: (-r['amount'], str(tuple(r.get(k) for k in keys))))


MATERIAL_COLUMNS = [('material_name', '材料名称'), ('material_code', '材料编号'),
                    ('specification', '规格'), ('detail_spec', '详细规格'), ('unit_name', '单位')]
AMOUNT_COLUMNS = [('goods', '材料金额（元）', 'money'), ('freight', '运费（元）', 'money'), ('amount', '合计（元）', 'money')]


def purchase_report(conn, f, scope):
    params = []
    condition = where_project('h.project_id', f, scope, params)
    condition += ' AND ' + dated('h.inquiry_date', f, params)
    headers = [dict(r) for r in conn.execute(f'''SELECT h.*, p.project_name
        FROM purchase_inquiries h LEFT JOIN projects p ON p.id=h.project_id
        WHERE {condition} AND h.approval_status='已同意' ORDER BY h.inquiry_date DESC, h.id DESC''', params)]
    # Restrict joined reads by the same dates and grants; do not scan every quote per item.
    base = f'''JOIN purchase_inquiries h ON h.id=i.inquiry_id WHERE {condition} AND h.approval_status='已同意' '''
    items = defaultdict(list)
    for row in conn.execute(f'''SELECT i.*, m.material_name, m.material_code, m.specification, u.unit_name
        FROM purchase_inquiry_items i LEFT JOIN materials m ON m.id=i.material_id
        LEFT JOIN units u ON u.id=m.unit_id {base} ORDER BY i.id''', params):
        items[row['inquiry_id']].append(dict(row))
    quotes = defaultdict(list)
    for row in conn.execute(f'''SELECT q.*, s.supplier_name FROM purchase_inquiry_quotes q
        JOIN purchase_inquiry_items i ON i.id=q.item_id LEFT JOIN suppliers s ON s.id=q.supplier_id
        {base} ORDER BY q.id''', params):
        quotes[row['item_id']].append(dict(row))
    freights = {(r['inquiry_id'], r['supplier_id']): money(r['tax_freight']) for r in conn.execute(f'''
        SELECT f.* FROM purchase_inquiry_supplier_freights f JOIN purchase_inquiries h ON h.id=f.inquiry_id
        WHERE {condition} AND h.approval_status='已同意' ''', params)}
    legacy_columns = {r[1] for r in conn.execute('PRAGMA table_info(purchase_inquiry_details)')}
    legacy = defaultdict(list)
    for row in conn.execute(f'''SELECT d.*, m.material_name, m.material_code, m.specification,
        u.unit_name, s.supplier_name FROM purchase_inquiry_details d
        JOIN purchase_inquiries h ON h.id=d.inquiry_id LEFT JOIN materials m ON m.id=d.material_id
        LEFT JOIN units u ON u.id=m.unit_id LEFT JOIN suppliers s ON s.id=d.supplier_id
        WHERE {condition} AND h.approval_status='已同意' ''', params):
        legacy[row['inquiry_id']].append(dict(row))
    rows, freight_rows, issues, orders = [], [], [], []
    for h in headers:
        common = {'order_id': h['id'], 'order_no': h['inquiry_no'], 'date': h['inquiry_date'],
                  'project_id': h['project_id'], 'project_name': h['project_name'] or '未关联项目'}
        selected, missing = [], 0
        for item in items[h['id']]:
            if item['quantity'] is None:
                missing += 1
                issues.append({**common, 'material_name': item['material_name'], 'note': '材料缺少询价数量，未计入金额'})
                continue
            candidates = quotes[item['id']]
            # selected_quote_id is a supplier ID in this application's saved form.
            supplier = h['selected_supplier_id'] or item['selected_quote_id']
            explicit = [q for q in candidates if q['is_selected']]
            if supplier:
                candidates = [q for q in candidates if q['supplier_id'] == supplier]
            elif explicit:
                candidates = explicit
            else:
                candidates = [q for q in candidates if q['is_lowest']]
            if len(candidates) != 1 or number(candidates[0]['tax_price']) <= 0:
                missing += 1
                issues.append({**common, 'material_name': item['material_name'], 'note': '缺失或存在多个有效选定报价，未计入金额'})
                continue
            q = candidates[0]
            selected.append({**common, **{k: item.get(k) for k in ['material_id', 'material_name', 'material_code', 'specification', 'detail_spec', 'unit_name']},
                             'quantity': item['quantity'], 'unit_price': q['tax_price'],
                             'supplier_id': q['supplier_id'], 'supplier_name': q['supplier_name'] or '供应商信息缺失',
                             'goods': money(number(item['quantity']) * number(q['tax_price'])), 'freight': 0})
        if not items[h['id']]:
            for item in legacy[h['id']]:
                if 'quantity' not in legacy_columns or item.get('quantity') is None:
                    missing += 1
                    issues.append({**common, 'material_name': item['material_name'], 'note': '旧版明细缺少数量，未推算金额'})
                    continue
                selected.append({**common, **item, 'goods': money(number(item['quantity']) * number(item['this_price'])),
                                 'unit_price': item['this_price'], 'freight': 0})
            if not legacy[h['id']]:
                issues.append({**common, 'note': '已审批单据缺少材料明细'})
        # Freight belongs to an order-supplier pair. Never repeat it on every material line.
        suppliers = {r['supplier_id']: r['supplier_name'] for r in selected}
        all_freight = [{**common, 'supplier_id': sid, 'supplier_name': name,
                        'goods': 0, 'quantity': 0, 'freight': freights.get((h['id'], sid), 0)} for sid, name in suppliers.items()]
        calculated = money(sum(number(r['goods']) for r in selected) + sum(number(r['freight']) for r in all_freight))
        difference = money(number(h['total_amount']) - number(calculated))
        if difference or missing:
            issues.append({**common, 'note': '单据总额与选定明细及运费存在差异', 'recorded': h['total_amount'], 'calculated': calculated, 'difference': difference})
        filtered = [r for r in selected if matches(r, f)]
        selected_ids = {r['supplier_id'] for r in filtered}
        # A material/unit filter cannot meaningfully allocate order-level freight.
        included_freight = [] if f['keyword'] or f['unit'] else [r for r in all_freight if r['supplier_id'] in selected_ids]
        rows.extend(filtered)
        freight_rows.extend(included_freight)
        if filtered or not (f['supplier_id'] or f['keyword'] or f['unit']):
            orders.append({**common, 'recorded': h['total_amount'], 'goods': money(sum(number(r['goods']) for r in filtered)),
                           'freight': money(sum(number(r['freight']) for r in included_freight)), 'difference': difference})
    all_rows = rows + freight_rows
    supplier_groups = groups(all_rows, ['supplier_id', 'supplier_name'])
    materials = groups(rows, ['material_id', 'material_name', 'material_code', 'specification', 'detail_spec', 'unit_name'])
    notes = ['采购按询价日期（含起止日）统计已同意单据；反映询价选定采购金额，不等同已入库或已付款金额。',
             '金额按选定报价单价×询价数量逐行保留两位小数；供应商笔数按“供应商＋询价单”去重，一单多家供应商时笔数合计可大于询价单数。',
             '材料按材料编号、规格、详细规格、单位分组；数量按单位分别排名，未做吨/公斤、米/根等换算。',
             '运费按询价单及选定供应商计一次；材料金额不分摊运费。旧版数量缺失、报价不明和单据金额差异均在核对明细中列出。']
    if f['keyword'] or f['unit']:
        notes.append('当前已筛选材料或单位：汇总仅含命中材料货款，运费不参与本次汇总。')
    notes.append('核对明细覆盖当前日期及项目内全部已同意单据，不受供应商、材料或单位筛选影响。')
    return {
        'notes': notes,
        'summary': [('询价单数', len(orders), 'count'), ('选定材料金额', money(sum(number(r['goods']) for r in rows)), 'money'),
                    ('选定运费', money(sum(number(r['freight']) for r in freight_rows)), 'money'),
                    ('选定合计', money(sum(number(r['goods']) + number(r['freight']) for r in all_rows)), 'money'),
                    ('供应商数', len(supplier_groups), 'count'), ('核对事项', len(issues), 'count')],
        'tables': [
            table('projects', '项目采购金额结构', [('project_name', '项目'), ('count', '询价笔数', 'number')] + AMOUNT_COLUMNS, groups(orders, ['project_id', 'project_name'])),
            table('supplier_counts', '供应商采购笔数排名', [('supplier_name', '供应商'), ('count', '采购笔数', 'number')] + AMOUNT_COLUMNS, sorted(supplier_groups, key=lambda r: (-r['count'], -r['amount'], r['supplier_id'] or 0))),
            table('supplier_amounts', '供应商采购金额排名', [('supplier_name', '供应商'), ('count', '采购笔数', 'number')] + AMOUNT_COLUMNS, supplier_groups),
            table('material_quantities', '材料数量排名（各单位内排名）', MATERIAL_COLUMNS + [('quantity', '数量', 'number'), ('goods', '材料金额（元）', 'money')], sorted(materials, key=lambda r: (r['unit_name'] or '', -r['quantity'], r['material_id'] or 0))),
            table('material_amounts', '材料金额排名', MATERIAL_COLUMNS + [('quantity', '数量', 'number'), ('goods', '材料金额（元）', 'money')], materials),
            table('details', '选定采购明细', [('order_no', '询价单号'), ('date', '询价日期'), ('project_name', '项目'), ('supplier_name', '供应商')] + MATERIAL_COLUMNS + [('quantity', '数量', 'number'), ('unit_price', '单价（元）', 'money'), ('goods', '材料金额（元）', 'money')], rows),
            table('freights', '选定供应商运费明细', [('order_no', '询价单号'), ('project_name', '项目'), ('supplier_name', '供应商'), ('freight', '运费（元）', 'money')], [r for r in freight_rows if r['freight']]),
            table('checks', '金额与缺失数据核对', [('order_no', '询价单号'), ('project_name', '项目'), ('material_name', '材料'), ('note', '核对事项'), ('recorded', '单据总额（元）', 'money'), ('calculated', '明细及运费（元）', 'money'), ('difference', '差额（元）', 'money')], issues),
        ]}


def operational_report(conn, f, scope):
    kind, params = f['kind'], []
    notes = []
    if kind in ('stock_in', 'stock_out'):
        direction = 'in' if kind == 'stock_in' else 'out'
        condition = where_project('h.project_id', f, scope, params) + ' AND ' + dated(f'h.{direction}_time', f, params)
        supplier = "COALESCE(d.supplier_id,h.supplier_id)" if direction == 'in' else 'NULL'
        sql = f'''SELECT d.id, h.id order_id, h.order_no, h.{direction}_time date, h.project_id, p.project_name,
            w.warehouse_name, m.material_name, m.material_code, m.specification, u.unit_name,
            d.quantity, d.unit_price, d.amount goods, 0 freight, {supplier} supplier_id, s.supplier_name
            FROM stock_{direction}_details d JOIN stock_{direction}_orders h ON h.id=d.order_id
            LEFT JOIN projects p ON p.id=h.project_id LEFT JOIN warehouses w ON w.id=h.warehouse_id
            LEFT JOIN materials m ON m.id=d.material_id LEFT JOIN units u ON u.id=m.unit_id
            LEFT JOIN suppliers s ON s.id={supplier} WHERE {condition} ORDER BY date DESC, d.id DESC'''
        notes.append('按实际入库/出库时间（含起止日）及单据明细金额统计；出入库金额不另加询价单运费。')
    elif kind == 'inventory':
        # Inventory is stored by warehouse+material, not by project. Use EXISTS
        # for related projects without multiplying or inventing per-project stock.
        project = where_project('h.project_id', f, scope, params)
        condition = f'''EXISTS (SELECT 1 FROM stock_in_details d JOIN stock_in_orders h ON h.id=d.order_id
            WHERE d.material_id=i.material_id AND h.warehouse_id=i.warehouse_id AND {project})'''
        if scope is None and not f['project_id']:
            condition = '1=1'
        sql = f'''SELECT i.id order_id, i.update_time date, w.warehouse_name, m.material_name, m.material_code,
            m.specification, m.detail_spec, u.unit_name, i.quantity, i.unit_price,
            i.quantity*i.unit_price goods, 0 freight
            FROM inventory i LEFT JOIN materials m ON m.id=i.material_id
            LEFT JOIN units u ON u.id=m.unit_id LEFT JOIN warehouses w ON w.id=i.warehouse_id
            WHERE i.quantity!=0 AND {condition} ORDER BY w.warehouse_name, m.material_code'''
        notes.append('当前库存快照，日期筛选不适用。金额=当前数量×库存单价。系统按仓库＋材料存量；项目筛选只选出该项目曾入库的同仓同材料，不代表项目独立库存。')
    elif kind == 'base_inventory':
        condition = where_project('i.source_project_id', f, scope, params)
        sql = f'''SELECT i.id order_id, i.update_time date, '材料基地' warehouse_name, p.project_name,
            COALESCE(m.material_name,i.material_name) material_name, m.material_code,
            COALESCE(m.specification,i.specification) specification, COALESCE(m.detail_spec,i.detail_spec) detail_spec,
            COALESCE(u.unit_name,i.unit_name) unit_name, i.region, i.quantity, i.unit_price,
            i.quantity*i.unit_price goods, 0 freight
            FROM base_inventory i LEFT JOIN materials m ON m.id=i.material_id
            LEFT JOIN units u ON u.id=m.unit_id LEFT JOIN projects p ON p.id=i.source_project_id
            WHERE i.quantity!=0 AND {condition} ORDER BY i.region, i.id'''
        notes.append('当前基地库存快照，日期筛选不适用。项目指来源项目；数量和金额按现存库存统计。')
    elif kind == 'transfers':
        condition = where_project('t.project_id', f, scope, params) + ' AND ' + dated('t.transfer_time', f, params)
        sql = f'''SELECT t.id, COALESCE(NULLIF(t.batch_no,''),t.transfer_no) order_id, t.transfer_no order_no,
            t.transfer_time date, t.project_id, p.project_name, t.material_name, t.specification, t.detail_spec,
            t.unit_name, t.quantity, t.depreciated_unit_price unit_price,
            t.quantity*t.depreciated_unit_price goods, t.freight
            FROM base_inventory_transfers t LEFT JOIN projects p ON p.id=t.project_id
            WHERE {condition} ORDER BY t.transfer_time DESC, t.id DESC'''
        notes.append('按调拨时间（含起止日）统计；项目指调入项目；金额=折旧单价×调拨数量＋调拨记录运费，笔数按批次（无批次则按调拨单号）去重。')
    else:
        condition = where_project('l.project_id', f, scope, params) + ' AND ' + dated('u.use_date', f, params)
        sql = f'''SELECT u.id order_id, u.usage_no order_no, u.use_date date, l.project_id, p.project_name,
            l.loan_no, u.expense_type, u.material_name, u.supplier_name, u.handler,
            u.amount goods, 0 freight, u.invoice_amount, u.is_reimbursed, u.reimbursed_at
            FROM petty_cash_usages u JOIN petty_cash_loans l ON l.id=u.loan_id
            LEFT JOIN projects p ON p.id=l.project_id WHERE {condition} ORDER BY u.use_date DESC, u.id DESC'''
        notes.append('按支出日期（含起止日）统计全部支出，包含已报销记录；已报销/未报销反映当前状态。期间支出不代表备用金余额，亦不与询价采购金额合并，避免重复。')
    rows = [dict(r) for r in conn.execute(sql, params)]
    rows = [r for r in rows if matches(r, f)]
    for row in rows:
        row['goods'], row['freight'] = money(row['goods']), money(row['freight'])
        row['amount'] = money(number(row['goods']) + number(row['freight']))
        if kind == 'cash':
            row['reimbursed_status'] = '已报销' if row['is_reimbursed'] else '未报销'
    columns = [('order_no', '单号'), ('date', '业务时间'), ('project_name', '项目')]
    if kind == 'stock_in':
        columns += [('supplier_name', '供应商'), ('warehouse_name', '仓库')]
    elif kind == 'stock_out':
        columns += [('warehouse_name', '仓库')]
    if kind in ('inventory', 'base_inventory'):
        columns = [('warehouse_name', '仓库'), ('project_name', '来源项目')] if kind == 'base_inventory' else [('warehouse_name', '仓库')]
        if kind == 'base_inventory':
            columns += [('region', '地区')]
        columns += [('date', '更新时间')]
    if kind == 'cash':
        columns += [('loan_no', '借款单号'), ('expense_type', '费用类型'), ('material_name', '材料'), ('supplier_name', '供应商'), ('handler', '经办人'), ('goods', '支出（元）', 'money'), ('invoice_amount', '发票金额（元）', 'money'), ('reimbursed_status', '当前报销状态')]
    else:
        columns += MATERIAL_COLUMNS + [('quantity', '数量', 'number'), ('unit_price', '单价（元）', 'money')] + AMOUNT_COLUMNS
    summary = [('记录条数', len(rows), 'count'), ('金额合计', money(sum(number(r['amount']) for r in rows)), 'money')]
    tables = []
    if kind not in ('inventory', 'base_inventory'):
        summary.insert(1, ('业务笔数', len({r['order_id'] for r in rows}), 'count'))
        amount_columns = [('goods', '支出金额（元）', 'money')] if kind == 'cash' else AMOUNT_COLUMNS
        tables.append(table('projects', '项目金额汇总', [('project_name', '项目'), ('count', '业务笔数', 'number')] + amount_columns, groups(rows, ['project_id', 'project_name'])))
    if kind == 'cash':
        summary += [('已报销支出', money(sum(number(r['goods']) for r in rows if r['is_reimbursed'])), 'money'),
                    ('未报销支出', money(sum(number(r['goods']) for r in rows if not r['is_reimbursed'])), 'money')]
        tables.append(table('expenses', '费用分类统计', [('expense_type', '费用类别'), ('count', '笔数', 'number'), ('goods', '支出金额（元）', 'money')], groups(rows, ['expense_type'])))
    else:
        tables.append(table('units', '按单位数量汇总', [('unit_name', '单位'), ('quantity', '数量', 'number'), ('goods', '材料金额（元）', 'money')], groups(rows, ['unit_name'])))
    tables.append(table('details', REPORT_NAMES[kind], columns, rows))
    return {'notes': notes, 'summary': summary, 'tables': tables}


def build_report(conn, f, scope):
    if f['kind'] not in ('purchase', 'stock_in') and f['supplier_id']:
        raise ValueError('当前报表不支持供应商筛选')
    if f['kind'] == 'cash' and f['unit']:
        raise ValueError('备用金报表不支持单位筛选')
    data = purchase_report(conn, f, scope) if f['kind'] == 'purchase' else operational_report(conn, f, scope)
    data.update(title=REPORT_NAMES[f['kind']], filters=f, generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    return data
