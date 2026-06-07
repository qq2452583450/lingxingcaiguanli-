"""
甲供材料专项量控管理
"""
from datetime import datetime

from flask import Blueprint, jsonify, request

from helpers import get_db
from helpers.auth_decorators import login_required, require_role


owner_supplied_bp = Blueprint('owner_supplied', __name__, url_prefix='/api/owner-supplied')

DEFAULT_SETTINGS = {
    'yellow_loss_rate': 0.02,
    'red_loss_rate': 0.03,
    'yellow_remaining_threshold': 0,
}


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _project_id():
    return request.args.get('project_id', type=int)


def _settings(cursor, project_id):
    if project_id:
        cursor.execute("""
            SELECT yellow_loss_rate, red_loss_rate, yellow_remaining_threshold
            FROM owner_supplied_settings WHERE project_id = ?
        """, (project_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
    return DEFAULT_SETTINGS.copy()


def _control_dict(row, settings):
    item = dict(row)
    current_control = _number(item['budget_quantity']) + _number(item['change_quantity'])
    book_inventory = _number(item['arrival_quantity']) - _number(item['issued_quantity'])
    remaining_requirement = current_control - _number(item['issued_quantity'])
    variance_quantity = (
        _number(item['issued_quantity'])
        - _number(item['theoretical_quantity'])
        - _number(item['site_surplus'])
    )
    theoretical_quantity = _number(item['theoretical_quantity'])
    loss_rate = variance_quantity / theoretical_quantity if theoretical_quantity else 0

    if remaining_requirement < 0 or loss_rate > _number(settings['red_loss_rate']):
        warning_status = '红色'
    elif (
        loss_rate > _number(settings['yellow_loss_rate'])
        or remaining_requirement <= _number(settings['yellow_remaining_threshold'])
    ):
        warning_status = '黄色'
    else:
        warning_status = '绿色'

    item.update({
        'current_control_quantity': current_control,
        'book_inventory': book_inventory,
        'remaining_requirement': remaining_requirement,
        'variance_quantity': variance_quantity,
        'variance_rate': loss_rate,
        'loss_rate': loss_rate,
        'warning_status': warning_status,
    })
    return item


def _list_controls(cursor, project_id=None):
    params = []
    where = ''
    if project_id:
        where = 'WHERE c.project_id = ?'
        params.append(project_id)
    cursor.execute(f"""
        SELECT c.*, p.project_name
        FROM owner_material_controls c
        LEFT JOIN projects p ON c.project_id = p.id
        {where}
        ORDER BY CASE c.control_level
            WHEN 'A类重点' THEN 1 WHEN 'B类常规' THEN 2 ELSE 3 END,
            c.updated_at DESC, c.id DESC
    """, params)
    return [_control_dict(row, _settings(cursor, row['project_id'])) for row in cursor.fetchall()]


def _required_text(data, *fields):
    return all(str(data.get(field, '')).strip() for field in fields)


@owner_supplied_bp.route('/summary', methods=['GET'])
@login_required
def get_summary():
    conn = get_db()
    cursor = conn.cursor()
    project_id = _project_id()
    controls = _list_controls(cursor, project_id)
    params = []
    where = ''
    if project_id:
        where = ' WHERE project_id = ?'
        params.append(project_id)
    cursor.execute(f"""
        SELECT closure_status, COUNT(*) AS count
        FROM owner_warning_issues{where}
        GROUP BY closure_status
    """, params)
    issue_counts = {row['closure_status']: row['count'] for row in cursor.fetchall()}
    return jsonify({'success': True, 'data': {
        'total': len(controls),
        'a_class': sum(1 for item in controls if item['control_level'] == 'A类重点'),
        'green': sum(1 for item in controls if item['warning_status'] == '绿色'),
        'yellow': sum(1 for item in controls if item['warning_status'] == '黄色'),
        'red': sum(1 for item in controls if item['warning_status'] == '红色'),
        'pending_issues': issue_counts.get('待处理', 0),
        'processing_issues': issue_counts.get('处理中', 0),
        'closed_issues': issue_counts.get('已闭环', 0),
    }})


@owner_supplied_bp.route('/controls', methods=['GET'])
@login_required
def get_controls():
    conn = get_db()
    controls = _list_controls(conn.cursor(), _project_id())
    return jsonify({'success': True, 'data': controls})


@owner_supplied_bp.route('/controls', methods=['POST'])
@require_role('系统管理员', '材料员')
def create_control():
    data = request.get_json() or {}
    if not data.get('project_id') or not _required_text(data, 'material_name', 'unit'):
        return jsonify({'success': False, 'message': '项目、材料名称和单位不能为空'})
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO owner_material_controls (
            project_id, data_status, control_level, building, work_item,
            material_name, specification, unit, contract_quantity,
            budget_quantity, change_quantity, arrival_quantity, issued_quantity,
            theoretical_quantity, site_surplus, contractor_inventory,
            transit_quantity, reason_measures, responsible_person, updated_at, remark
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data['project_id'], data.get('data_status', '正式'),
        data.get('control_level', 'A类重点'), data.get('building', ''),
        data.get('work_item', ''), data.get('material_name', ''),
        data.get('specification', ''), data.get('unit', ''),
        _number(data.get('contract_quantity')), _number(data.get('budget_quantity')),
        _number(data.get('change_quantity')), _number(data.get('arrival_quantity')),
        _number(data.get('issued_quantity')), _number(data.get('theoretical_quantity')),
        _number(data.get('site_surplus')), _number(data.get('contractor_inventory')),
        _number(data.get('transit_quantity')), data.get('reason_measures', ''),
        data.get('responsible_person', ''), now, data.get('remark', ''),
    ))
    conn.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid})


@owner_supplied_bp.route('/controls/<int:item_id>', methods=['PUT'])
@require_role('系统管理员', '材料员')
def update_control(item_id):
    data = request.get_json() or {}
    if not _required_text(data, 'material_name', 'unit'):
        return jsonify({'success': False, 'message': '材料名称和单位不能为空'})
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    conn.execute("""
        UPDATE owner_material_controls SET
            data_status = ?, control_level = ?, building = ?, work_item = ?,
            material_name = ?, specification = ?, unit = ?, contract_quantity = ?,
            budget_quantity = ?, change_quantity = ?, arrival_quantity = ?,
            issued_quantity = ?, theoretical_quantity = ?, site_surplus = ?,
            contractor_inventory = ?, transit_quantity = ?, reason_measures = ?,
            responsible_person = ?, updated_at = ?, remark = ?
        WHERE id = ?
    """, (
        data.get('data_status', '正式'), data.get('control_level', 'A类重点'),
        data.get('building', ''), data.get('work_item', ''),
        data.get('material_name', ''), data.get('specification', ''),
        data.get('unit', ''), _number(data.get('contract_quantity')),
        _number(data.get('budget_quantity')), _number(data.get('change_quantity')),
        _number(data.get('arrival_quantity')), _number(data.get('issued_quantity')),
        _number(data.get('theoretical_quantity')), _number(data.get('site_surplus')),
        _number(data.get('contractor_inventory')), _number(data.get('transit_quantity')),
        data.get('reason_measures', ''), data.get('responsible_person', ''),
        now, data.get('remark', ''), item_id,
    ))
    conn.commit()
    return jsonify({'success': True})


@owner_supplied_bp.route('/controls/<int:item_id>', methods=['DELETE'])
@require_role('系统管理员', '材料员')
def delete_control(item_id):
    conn = get_db()
    conn.execute('DELETE FROM owner_material_controls WHERE id = ?', (item_id,))
    conn.commit()
    return jsonify({'success': True})


@owner_supplied_bp.route('/demands', methods=['GET'])
@login_required
def get_demands():
    conn = get_db()
    cursor = conn.cursor()
    params = []
    where = ''
    if _project_id():
        where = 'WHERE d.project_id = ?'
        params.append(_project_id())
    cursor.execute(f"""
        SELECT d.*, p.project_name
        FROM owner_monthly_demands d
        LEFT JOIN projects p ON d.project_id = p.id
        {where}
        ORDER BY d.plan_month DESC, d.required_date ASC, d.id DESC
    """, params)
    items = []
    for row in cursor.fetchall():
        item = dict(row)
        item['recommended_supply'] = max(
            0,
            _number(item['planned_quantity'])
            - _number(item['current_inventory'])
            - _number(item['contractor_inventory'])
            - _number(item['transit_quantity'])
        )
        items.append(item)
    return jsonify({'success': True, 'data': items})


@owner_supplied_bp.route('/demands', methods=['POST'])
@require_role('系统管理员', '材料员')
def create_demand():
    data = request.get_json() or {}
    if not data.get('project_id') or not _required_text(data, 'plan_month', 'material_name', 'unit'):
        return jsonify({'success': False, 'message': '项目、计划月份、材料名称和单位不能为空'})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO owner_monthly_demands (
            project_id, plan_month, building, construction_area, material_name,
            specification, unit, planned_quantity, current_inventory,
            contractor_inventory, transit_quantity, required_date, review_comment
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data['project_id'], data['plan_month'], data.get('building', ''),
        data.get('construction_area', ''), data.get('material_name', ''),
        data.get('specification', ''), data.get('unit', ''),
        _number(data.get('planned_quantity')), _number(data.get('current_inventory')),
        _number(data.get('contractor_inventory')), _number(data.get('transit_quantity')),
        data.get('required_date') or None, data.get('review_comment', ''),
    ))
    conn.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid})


@owner_supplied_bp.route('/demands/<int:item_id>', methods=['DELETE'])
@require_role('系统管理员', '材料员')
def delete_demand(item_id):
    conn = get_db()
    conn.execute('DELETE FROM owner_monthly_demands WHERE id = ?', (item_id,))
    conn.commit()
    return jsonify({'success': True})


@owner_supplied_bp.route('/transactions', methods=['GET'])
@login_required
def get_transactions():
    conn = get_db()
    cursor = conn.cursor()
    params = []
    where = ''
    if _project_id():
        where = 'WHERE t.project_id = ?'
        params.append(_project_id())
    cursor.execute(f"""
        SELECT t.*, p.project_name
        FROM owner_material_transactions t
        LEFT JOIN projects p ON t.project_id = p.id
        {where}
        ORDER BY t.business_date DESC, t.id DESC
    """, params)
    return jsonify({'success': True, 'data': [dict(row) for row in cursor.fetchall()]})


@owner_supplied_bp.route('/transactions', methods=['POST'])
@require_role('系统管理员', '材料员')
def create_transaction():
    data = request.get_json() or {}
    if not data.get('project_id') or not _required_text(data, 'business_date', 'business_type', 'material_name', 'unit'):
        return jsonify({'success': False, 'message': '项目、业务日期、业务类型、材料名称和单位不能为空'})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO owner_material_transactions (
            project_id, business_date, business_type, building, construction_area,
            material_name, specification, unit, quantity, supplier_source,
            document_no, acceptance_result, quality_documents, receiving_unit,
            signer, registrant, remark
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data['project_id'], data['business_date'], data['business_type'],
        data.get('building', ''), data.get('construction_area', ''),
        data.get('material_name', ''), data.get('specification', ''),
        data.get('unit', ''), _number(data.get('quantity')),
        data.get('supplier_source', ''), data.get('document_no', ''),
        data.get('acceptance_result', ''), data.get('quality_documents', ''),
        data.get('receiving_unit', ''), data.get('signer', ''),
        data.get('registrant', ''), data.get('remark', ''),
    ))
    conn.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid})


@owner_supplied_bp.route('/transactions/<int:item_id>', methods=['DELETE'])
@require_role('系统管理员', '材料员')
def delete_transaction(item_id):
    conn = get_db()
    conn.execute('DELETE FROM owner_material_transactions WHERE id = ?', (item_id,))
    conn.commit()
    return jsonify({'success': True})


@owner_supplied_bp.route('/issues', methods=['GET'])
@login_required
def get_issues():
    conn = get_db()
    cursor = conn.cursor()
    params = []
    where = ''
    if _project_id():
        where = 'WHERE i.project_id = ?'
        params.append(_project_id())
    cursor.execute(f"""
        SELECT i.*, p.project_name
        FROM owner_warning_issues i
        LEFT JOIN projects p ON i.project_id = p.id
        {where}
        ORDER BY CASE i.closure_status WHEN '待处理' THEN 1 WHEN '处理中' THEN 2 ELSE 3 END,
            i.warning_date DESC, i.id DESC
    """, params)
    return jsonify({'success': True, 'data': [dict(row) for row in cursor.fetchall()]})


@owner_supplied_bp.route('/issues', methods=['POST'])
@require_role('系统管理员', '材料员')
def create_issue():
    data = request.get_json() or {}
    if not data.get('project_id') or not _required_text(data, 'warning_date', 'warning_status', 'material_name', 'problem_description'):
        return jsonify({'success': False, 'message': '项目、预警日期、状态、材料名称和问题描述不能为空'})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO owner_warning_issues (
            project_id, warning_date, warning_status, building, material_name,
            specification, variance_quantity, loss_rate, problem_description,
            reason_category, corrective_action, responsible_person, due_date,
            closure_status, review_result, reviewer
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data['project_id'], data['warning_date'], data['warning_status'],
        data.get('building', ''), data.get('material_name', ''),
        data.get('specification', ''), _number(data.get('variance_quantity')),
        _number(data.get('loss_rate')), data.get('problem_description', ''),
        data.get('reason_category', ''), data.get('corrective_action', ''),
        data.get('responsible_person', ''), data.get('due_date') or None,
        data.get('closure_status', '待处理'), data.get('review_result', ''),
        data.get('reviewer', ''),
    ))
    conn.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid})


@owner_supplied_bp.route('/issues/<int:item_id>', methods=['PUT'])
@require_role('系统管理员', '材料员')
def update_issue(item_id):
    data = request.get_json() or {}
    conn = get_db()
    conn.execute("""
        UPDATE owner_warning_issues SET closure_status = ?, review_result = ?, reviewer = ?
        WHERE id = ?
    """, (
        data.get('closure_status', '待处理'), data.get('review_result', ''),
        data.get('reviewer', ''), item_id,
    ))
    conn.commit()
    return jsonify({'success': True})


@owner_supplied_bp.route('/issues/<int:item_id>', methods=['DELETE'])
@require_role('系统管理员', '材料员')
def delete_issue(item_id):
    conn = get_db()
    conn.execute('DELETE FROM owner_warning_issues WHERE id = ?', (item_id,))
    conn.commit()
    return jsonify({'success': True})

