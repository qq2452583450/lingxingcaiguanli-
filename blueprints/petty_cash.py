"""
备用金管理蓝图
"""
import os
import re
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, session, send_from_directory
from werkzeug.utils import secure_filename

from helpers import get_db
from helpers.auth_decorators import login_required


petty_cash_bp = Blueprint('petty_cash', __name__, url_prefix='/api/petty-cash')

ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.pdf'}
DEFAULT_UPLOAD_DIR = r'C:\备用金'
EXPENSE_TYPES = ('维修费', '加油费', '极小金额零星材购买', '其他')


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _upload_root():
    return Path(os.environ.get('PETTY_CASH_UPLOAD_DIR') or DEFAULT_UPLOAD_DIR)


def _clean_part(value, fallback='未命名'):
    text = str(value or fallback).strip() or fallback
    text = re.sub(r'[\\/:*?"<>|\s]+', '_', text)
    return text.strip('_') or fallback


def _file_ext(filename):
    return Path(filename or '').suffix.lower()


def _save_upload(file_storage, project_name, business_date, creator_name, *parts):
    if not file_storage or not file_storage.filename:
        return None, None
    ext = _file_ext(file_storage.filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError('只允许上传图片或PDF文件')

    root = _upload_root()
    root.mkdir(parents=True, exist_ok=True)
    original_name = secure_filename(file_storage.filename) or f'file{ext}'
    name_parts = [_clean_part(project_name), _clean_part(business_date), _clean_part(creator_name)]
    name_parts.extend(_clean_part(part) for part in parts if part)
    filename = '_'.join(name_parts + [original_name])
    path = root / filename
    counter = 1
    while path.exists():
        filename = '_'.join(name_parts + [f'{counter}_{original_name}'])
        path = root / filename
        counter += 1
    file_storage.save(path)
    return str(path), filename


def _project(cursor, project_id):
    cursor.execute("SELECT id, project_name FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def _next_no(cursor, table_name, column_name, prefix, date_value):
    date_digits = (date_value or datetime.now().strftime('%Y-%m-%d')).replace('-', '')
    like = f'{prefix}-{date_digits}-%'
    cursor.execute(
        f"SELECT {column_name} FROM {table_name} WHERE {column_name} LIKE ? ORDER BY {column_name} DESC LIMIT 1",
        (like,),
    )
    row = cursor.fetchone()
    seq = 1
    if row:
        try:
            seq = int(row[0].rsplit('-', 1)[-1]) + 1
        except (TypeError, ValueError):
            seq = 1
    return f'{prefix}-{date_digits}-{seq:03d}'


def _loan_balance(cursor, loan_id):
    cursor.execute("SELECT total_amount FROM petty_cash_loans WHERE id = ?", (loan_id,))
    row = cursor.fetchone()
    if not row:
        return None
    total = _number(row['total_amount'])
    cursor.execute("SELECT COALESCE(SUM(amount), 0) AS used_amount FROM petty_cash_usages WHERE loan_id = ?", (loan_id,))
    used = _number(cursor.fetchone()['used_amount'])
    return total, used, total - used


def _loan_row(row):
    item = dict(row)
    total = _number(item.get('total_amount'))
    used = _number(item.get('used_amount'))
    item['total_amount'] = total
    item['used_amount'] = used
    item['balance_amount'] = total - used
    return item


@petty_cash_bp.route('/summary', methods=['GET'])
@login_required
def get_summary():
    project_id = request.args.get('project_id', type=int)
    params = []
    where = ''
    if project_id:
        where = 'WHERE l.project_id = ?'
        params.append(project_id)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT
            COALESCE(SUM(l.total_amount), 0) AS total_amount,
            COALESCE((SELECT SUM(u.amount)
                      FROM petty_cash_usages u
                      JOIN petty_cash_loans l2 ON u.loan_id = l2.id
                      {'WHERE l2.project_id = ?' if project_id else ''}), 0) AS used_amount,
            COUNT(DISTINCT l.id) AS loan_count,
            COALESCE((SELECT COUNT(*)
                      FROM petty_cash_usages u
                      JOIN petty_cash_loans l3 ON u.loan_id = l3.id
                      {'WHERE l3.project_id = ?' if project_id else ''}), 0) AS usage_count
        FROM petty_cash_loans l
        {where}
    """, [*params, *params, *params])
    row = dict(cursor.fetchone())
    total = _number(row['total_amount'])
    used = _number(row['used_amount'])
    return jsonify({'success': True, 'data': {
        'total_amount': total,
        'used_amount': used,
        'balance_amount': total - used,
        'loan_count': int(row['loan_count'] or 0),
        'usage_count': int(row['usage_count'] or 0),
    }})


@petty_cash_bp.route('/loans', methods=['GET'])
@login_required
def get_loans():
    project_id = request.args.get('project_id', type=int)
    params = []
    where = ''
    if project_id:
        where = 'WHERE l.project_id = ?'
        params.append(project_id)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT l.*, p.project_name, u.real_name AS creator_name,
               COALESCE(SUM(pc.amount), 0) AS used_amount
        FROM petty_cash_loans l
        LEFT JOIN projects p ON l.project_id = p.id
        LEFT JOIN users u ON l.creator_id = u.id
        LEFT JOIN petty_cash_usages pc ON pc.loan_id = l.id
        {where}
        GROUP BY l.id
        ORDER BY l.loan_date DESC, l.id DESC
    """, params)
    return jsonify({'success': True, 'data': [_loan_row(row) for row in cursor.fetchall()]})


@petty_cash_bp.route('/loans', methods=['POST'])
@login_required
def create_loan():
    user = session.get('user') or {}
    project_id = request.form.get('project_id', type=int)
    loan_date = request.form.get('loan_date') or datetime.now().strftime('%Y-%m-%d')
    total_amount = _number(request.form.get('total_amount'))
    remark = request.form.get('remark', '')
    if not project_id or total_amount <= 0:
        return jsonify({'success': False, 'message': '项目和借款总额不能为空'})

    conn = get_db()
    cursor = conn.cursor()
    project = _project(cursor, project_id)
    if not project:
        return jsonify({'success': False, 'message': '项目不存在'})

    try:
        loan_no = _next_no(cursor, 'petty_cash_loans', 'loan_no', 'BYJ', loan_date)
        file_path, file_name = _save_upload(
            request.files.get('payment_file'),
            project['project_name'],
            loan_date,
            user.get('real_name') or user.get('username') or '创建者',
        )
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT INTO petty_cash_loans (
                loan_no, project_id, loan_date, total_amount, payment_file_path,
                payment_file_name, creator_id, remark, create_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            loan_no, project_id, loan_date, total_amount, file_path, file_name,
            user.get('id'), remark, now,
        ))
        conn.commit()
        return jsonify({'success': True, 'id': cursor.lastrowid, 'loan_no': loan_no})
    except ValueError as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)})


@petty_cash_bp.route('/loans/<int:loan_id>', methods=['DELETE'])
@login_required
def delete_loan(loan_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS c FROM petty_cash_usages WHERE loan_id = ?", (loan_id,))
    if cursor.fetchone()['c']:
        return jsonify({'success': False, 'message': '该备用金已有使用明细，不能直接删除'})
    cursor.execute("DELETE FROM petty_cash_loans WHERE id = ?", (loan_id,))
    conn.commit()
    return jsonify({'success': True})


@petty_cash_bp.route('/usages', methods=['GET'])
@login_required
def get_usages():
    project_id = request.args.get('project_id', type=int)
    loan_id = request.args.get('loan_id', type=int)
    expense_type = request.args.get('expense_type', '')
    where = []
    params = []
    if project_id:
        where.append('l.project_id = ?')
        params.append(project_id)
    if loan_id:
        where.append('u.loan_id = ?')
        params.append(loan_id)
    if expense_type:
        where.append('u.expense_type = ?')
        params.append(expense_type)
    where_sql = 'WHERE ' + ' AND '.join(where) if where else ''
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT u.*, l.loan_no, p.project_name
        FROM petty_cash_usages u
        JOIN petty_cash_loans l ON u.loan_id = l.id
        LEFT JOIN projects p ON l.project_id = p.id
        {where_sql}
        ORDER BY u.use_date DESC, u.id DESC
    """, params)
    rows = []
    for row in cursor.fetchall():
        item = dict(row)
        item['amount'] = _number(item.get('amount'))
        rows.append(item)
    return jsonify({'success': True, 'data': rows})


@petty_cash_bp.route('/usages', methods=['POST'])
@login_required
def create_usage():
    user = session.get('user') or {}
    loan_id = request.form.get('loan_id', type=int)
    use_date = request.form.get('use_date') or datetime.now().strftime('%Y-%m-%d')
    expense_type = request.form.get('expense_type') or '其他'
    amount = _number(request.form.get('amount'))
    handler = request.form.get('handler', '')
    description = request.form.get('description', '')
    if not loan_id or amount <= 0:
        return jsonify({'success': False, 'message': '备用金和使用金额不能为空'})
    if expense_type not in EXPENSE_TYPES:
        expense_type = '其他'

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.*, p.project_name
        FROM petty_cash_loans l
        LEFT JOIN projects p ON l.project_id = p.id
        WHERE l.id = ?
    """, (loan_id,))
    loan = cursor.fetchone()
    if not loan:
        return jsonify({'success': False, 'message': '备用金记录不存在'})
    balance = _loan_balance(cursor, loan_id)
    if balance and amount > balance[2]:
        return jsonify({'success': False, 'message': '余额不足，不能超过现有金额'})

    try:
        usage_no = _next_no(cursor, 'petty_cash_usages', 'usage_no', 'BYJMX', use_date)
        file_path, file_name = _save_upload(
            request.files.get('proof_file'),
            loan['project_name'],
            use_date,
            user.get('real_name') or user.get('username') or '创建者',
            expense_type,
        )
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT INTO petty_cash_usages (
                usage_no, loan_id, use_date, expense_type, amount, handler,
                description, proof_file_path, proof_file_name, creator_id, create_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            usage_no, loan_id, use_date, expense_type, amount, handler,
            description, file_path, file_name, user.get('id'), now,
        ))
        conn.commit()
        return jsonify({'success': True, 'id': cursor.lastrowid, 'usage_no': usage_no})
    except ValueError as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)})


@petty_cash_bp.route('/usages/<int:usage_id>', methods=['DELETE'])
@login_required
def delete_usage(usage_id):
    conn = get_db()
    conn.execute("DELETE FROM petty_cash_usages WHERE id = ?", (usage_id,))
    conn.commit()
    return jsonify({'success': True})


@petty_cash_bp.route('/files/<path:filename>', methods=['GET'])
@login_required
def get_file(filename):
    return send_from_directory(_upload_root(), filename, as_attachment=False)

