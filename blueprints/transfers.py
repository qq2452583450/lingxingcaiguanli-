"""
材料调拨蓝图（仓库/存放点之间的库存移动）
"""
from datetime import datetime
from html import escape
import os
import shutil
from pathlib import Path

from flask import Blueprint, jsonify, request, session, send_from_directory
from werkzeug.utils import secure_filename

from helpers import get_db
from helpers.order_no_generator import generate_stock_transfer_no


transfer_bp = Blueprint('transfer', __name__, url_prefix='/api')
BASE_INVENTORY_REGIONS = ('成都', '云南', '广西')
BASE_ATTACHMENT_MAX_FILES = 9
BASE_ATTACHMENT_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.pdf'}


def _base_attachment_root():
    return Path(os.environ.get('BASE_ATTACHMENT_UPLOAD_DIR') or r'C:\材料基地附件')


def _ensure_attachment_tables(cursor):
    cursor.execute("""CREATE TABLE IF NOT EXISTS base_inventory_attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, base_inventory_id INTEGER NOT NULL,
        file_path TEXT NOT NULL, file_name TEXT NOT NULL, uploader_id INTEGER, create_time TEXT)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS base_transfer_attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, transfer_key TEXT NOT NULL,
        file_path TEXT NOT NULL, file_name TEXT NOT NULL, uploader_id INTEGER, create_time TEXT)""")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_base_inventory_attachments_inventory ON base_inventory_attachments(base_inventory_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_base_transfer_attachments_key ON base_transfer_attachments(transfer_key)")


def _attachment_files():
    return [item for item in request.files.getlist('files') if item and item.filename]


def _save_attachment(file_storage, prefix):
    extension = Path(file_storage.filename).suffix.lower()
    if extension not in BASE_ATTACHMENT_EXTENSIONS:
        raise ValueError('仅支持上传图片或PDF附件')
    root = _base_attachment_root()
    root.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(file_storage.filename) or f'attachment{extension}'
    stamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    target = root / f'{prefix}_{stamp}_{filename}'
    file_storage.save(target)
    return str(target), filename


def _copy_inventory_attachments_to_transfer(cursor, base_inventory_id, transfer_key, uploader_id):
    _ensure_attachment_tables(cursor)
    cursor.execute(
        'SELECT file_path, file_name FROM base_inventory_attachments WHERE base_inventory_id = ?',
        (base_inventory_id,),
    )
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for row in cursor.fetchall():
        source = Path(row['file_path'])
        if not source.is_file():
            continue
        target = _base_attachment_root() / f'base_transfer_{transfer_key}_{datetime.now().strftime("%Y%m%d%H%M%S%f")}_{source.name}'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        cursor.execute(
            'INSERT INTO base_transfer_attachments (transfer_key, file_path, file_name, uploader_id, create_time) VALUES (?, ?, ?, ?, ?)',
            (transfer_key, str(target), row['file_name'], uploader_id, now),
        )


def _current_user():
    return session.get('user')


def _can_manage_stock(user):
    return user and user.get('role_name') in ('系统管理员', '材料员', '基地负责人')


def _get_base_inventory_region(data):
    region = (data.get('region') or '成都').strip()
    if region not in BASE_INVENTORY_REGIONS:
        return None, '地区只能选择成都、云南或广西'
    return region, None


def _get_base_warehouse(cursor, create_if_missing=False):
    """使用默认仓库作为唯一材料基地，兼容已有库存数据。"""
    cursor.execute("""
        SELECT id, warehouse_name
        FROM warehouses
        ORDER BY is_default DESC, id ASC
        LIMIT 1
    """)
    warehouse = cursor.fetchone()
    if warehouse or not create_if_missing:
        return warehouse

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        INSERT INTO warehouses (warehouse_name, address, remark, is_default, create_time)
        VALUES ('材料基地', '', '材料调拨基地', 1, ?)
    """, (now,))
    return {'id': cursor.lastrowid, 'warehouse_name': '材料基地'}


def _generate_base_transfer_no(reserved=None):
    """Generate a JDB number across visible batch numbers and hidden detail numbers."""
    reserved = set(reserved or [])
    today = datetime.now().strftime('%y%m%d')
    like_pattern = f'JDB-{today}-%'
    conn = get_db()
    cursor = conn.cursor()
    max_seq = 0
    for column_name in ('transfer_no', 'batch_no'):
        cursor.execute(f"""
            SELECT {column_name}
            FROM base_inventory_transfers
            WHERE {column_name} LIKE ?
            ORDER BY {column_name} DESC
            LIMIT 1
        """, (like_pattern,))
        row = cursor.fetchone()
        if row and row[0]:
            try:
                max_seq = max(max_seq, int(str(row[0]).split('-')[-1]))
            except (TypeError, ValueError):
                pass

    while True:
        max_seq += 1
        transfer_no = f'JDB-{today}-{max_seq:03d}'
        if transfer_no in reserved:
            continue
        cursor.execute("""
            SELECT 1
            FROM base_inventory_transfers
            WHERE transfer_no = ? OR batch_no = ?
            LIMIT 1
        """, (transfer_no, transfer_no))
        if not cursor.fetchone():
            return transfer_no


@transfer_bp.route('/base-inventory', methods=['GET'])
def get_base_inventory():
    """获取材料基地库存台账。"""
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'message': '无权限查看基地库存'})

    conn = get_db()
    cursor = conn.cursor()
    _ensure_attachment_tables(cursor)
    cursor.execute("""
        SELECT bi.id, bi.material_id, bi.quantity, bi.unit_price, bi.update_time, bi.remark,
               COALESCE(NULLIF(bi.region, ''), '成都') AS region,
               COALESCE(m.material_code, '基地自有') AS material_code,
               COALESCE(m.material_name, bi.material_name) AS material_name,
               COALESCE(m.specification, bi.specification) AS specification,
               COALESCE(m.detail_spec, bi.detail_spec) AS detail_spec,
               COALESCE(u.unit_name, bi.unit_name) AS unit_name,
               (SELECT COUNT(*) FROM base_inventory_attachments bia
                WHERE bia.base_inventory_id = bi.id) AS attachment_count
        FROM base_inventory bi
        LEFT JOIN materials m ON bi.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        WHERE bi.quantity != 0
        ORDER BY COALESCE(NULLIF(bi.region, ''), '成都') ASC, m.material_code ASC
    """)
    return jsonify({
        'success': True,
        'data': [dict(row) for row in cursor.fetchall()],
        'warehouse_name': '材料基地',
    })


@transfer_bp.route('/base-inventory/<int:base_inventory_id>', methods=['DELETE'])
def delete_base_inventory(base_inventory_id):
    """删除基地库存记录。"""
    user = _current_user()
    if not _can_manage_stock(user):
        return jsonify({'success': False, 'message': '无权限删除基地库存'})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM base_inventory WHERE id = ?", (base_inventory_id,))
    inventory = cursor.fetchone()
    if not inventory:
        return jsonify({'success': False, 'message': '基地库存记录不存在'})

    cursor.execute("DELETE FROM base_inventory WHERE id = ?", (base_inventory_id,))
    conn.commit()
    return jsonify({
        'success': True,
        'message': f'基地库存记录已删除',
    })


@transfer_bp.route('/base-inventory/<int:base_inventory_id>', methods=['PUT'])
def update_base_inventory(base_inventory_id):
    """编辑基地库存记录。"""
    user = _current_user()
    if not _can_manage_stock(user):
        return jsonify({'success': False, 'message': '无权限编辑基地库存'})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM base_inventory WHERE id = ?", (base_inventory_id,))
    inventory = cursor.fetchone()
    if not inventory:
        return jsonify({'success': False, 'message': '基地库存记录不存在'})

    data = request.json or {}
    try:
        quantity = float(data.get('quantity'))
        unit_price = float(data.get('unit_price') or 0)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '请填写有效的数量和单价'})
    if quantity <= 0:
        return jsonify({'success': False, 'message': '数量必须大于0'})
    if unit_price < 0:
        return jsonify({'success': False, 'message': '单价不能小于0'})

    material_name = (data.get('material_name') or '').strip()
    specification = (data.get('specification') or '').strip()
    detail_spec = (data.get('detail_spec') or '').strip()
    unit_name = (data.get('unit_name') or '').strip()
    region, region_error = _get_base_inventory_region(data)
    if region_error:
        return jsonify({'success': False, 'message': region_error})
    remark = escape((data.get('remark') or '').strip())

    if not material_name:
        return jsonify({'success': False, 'message': '请填写材料名称'})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        cursor.execute("""
            UPDATE base_inventory
            SET material_name = ?, specification = ?, detail_spec = ?,
                unit_name = ?, region = ?, quantity = ?, unit_price = ?,
                update_time = ?, remark = ?
            WHERE id = ?
        """, (material_name, specification, detail_spec, unit_name, region,
              quantity, unit_price, now, remark, base_inventory_id))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if 'UNIQUE' in str(exc).upper():
            return jsonify({'success': False, 'message': '该材料在此地区已有基地库存记录'})
        return jsonify({'success': False, 'message': str(exc)})
    return jsonify({'success': True, 'message': f'「{material_name}」已更新'})


@transfer_bp.route('/base-inventory', methods=['POST'])
def stock_in_base_inventory():
    """将已有材料补录或快捷入库到材料基地。"""
    user = _current_user()
    if not _can_manage_stock(user):
        return jsonify({'success': False, 'message': '无权限操作基地库存'})

    data = request.json or {}
    try:
        quantity = float(data.get('quantity'))
        unit_price = float(data.get('unit_price') or 0)
        material_id = (
            int(data.get('material_id'))
            if data.get('material_id') not in (None, '')
            else None
        )
        source_warehouse_id = (
            int(data.get('source_warehouse_id'))
            if data.get('source_warehouse_id') not in (None, '')
            else None
        )
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '请填写有效的基地材料信息'})
    if quantity <= 0:
        return jsonify({'success': False, 'message': '入库数量必须大于0'})
    if unit_price < 0:
        return jsonify({'success': False, 'message': '单价不能小于0'})

    conn = get_db()
    cursor = conn.cursor()
    material_name = (data.get('material_name') or '').strip()
    specification = (data.get('specification') or '').strip()
    detail_spec = (data.get('detail_spec') or '').strip()
    unit_name = (data.get('unit_name') or '').strip()
    region, region_error = _get_base_inventory_region(data)
    if region_error:
        return jsonify({'success': False, 'message': region_error})
    remark = escape((data.get('remark') or '').strip())

    if material_id is not None:
        cursor.execute("SELECT material_name FROM materials WHERE id = ?", (material_id,))
        material = cursor.fetchone()
        if not material:
            return jsonify({'success': False, 'message': '材料不存在，请刷新后重试'})
        material_name = material['material_name']
    elif not material_name:
        return jsonify({'success': False, 'message': '请填写材料名称'})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if source_warehouse_id is not None:
        cursor.execute("""
            SELECT quantity
            FROM inventory
            WHERE material_id = ? AND warehouse_id = ?
        """, (material_id, source_warehouse_id))
        source_inventory = cursor.fetchone()
        if not source_inventory or source_inventory['quantity'] < quantity:
            return jsonify({'success': False, 'message': '本项目库存不足，无法入库基地'})
        cursor.execute("""
            UPDATE inventory
            SET quantity = quantity - ?, update_time = ?
            WHERE material_id = ? AND warehouse_id = ?
        """, (quantity, now, material_id, source_warehouse_id))

    if material_id is not None:
        cursor.execute("""
            INSERT INTO base_inventory (material_id, region, quantity, unit_price, update_time, remark)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(material_id, region) DO UPDATE SET
                quantity = quantity + excluded.quantity,
                unit_price = CASE
                    WHEN excluded.unit_price > 0 THEN excluded.unit_price
                    ELSE base_inventory.unit_price
                END,
                update_time = excluded.update_time,
                remark = CASE
                    WHEN ? != '' THEN ?
                    ELSE base_inventory.remark
                END
        """, (material_id, region, quantity, unit_price, now, remark, remark, remark))
    else:
        cursor.execute("""
            SELECT id
            FROM base_inventory
            WHERE material_id IS NULL
              AND material_name = ?
              AND COALESCE(specification, '') = ?
              AND COALESCE(detail_spec, '') = ?
              AND COALESCE(unit_name, '') = ?
              AND COALESCE(region, '成都') = ?
        """, (material_name, specification, detail_spec, unit_name, region))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("""
                UPDATE base_inventory
                SET quantity = quantity + ?,
                    unit_price = CASE WHEN ? > 0 THEN ? ELSE unit_price END,
                    update_time = ?,
                    remark = CASE WHEN ? != '' THEN ? ELSE remark END
                WHERE id = ?
            """, (quantity, unit_price, unit_price, now, remark, remark, existing['id']))
        else:
            cursor.execute("""
                INSERT INTO base_inventory (
                    material_name, specification, detail_spec, unit_name, region,
                    quantity, unit_price, update_time, remark
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (material_name, specification, detail_spec, unit_name, region, quantity, unit_price, now, remark))
    conn.commit()
    return jsonify({
        'success': True,
        'message': f'「{material_name}」已入库基地',
    })


@transfer_bp.route('/base-transfers', methods=['GET'])
def get_base_transfers():
    """获取基地到项目调拨记录。"""
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'message': '无权限查看基地调拨记录'})

    conn = get_db()
    cursor = conn.cursor()
    _ensure_attachment_tables(cursor)
    cursor.execute("""
        SELECT bit.*, p.project_name, operator.real_name AS operator_name,
               (SELECT COUNT(*) FROM base_transfer_attachments bta
                WHERE bta.transfer_key = COALESCE(bit.batch_no, bit.transfer_no)) AS attachment_count
        FROM base_inventory_transfers bit
        JOIN projects p ON bit.project_id = p.id
        LEFT JOIN users operator ON bit.operator_id = operator.id
        ORDER BY bit.transfer_time DESC, bit.id DESC
    """)
    return jsonify({'success': True, 'data': [dict(row) for row in cursor.fetchall()]})


@transfer_bp.route('/base-inventory/<int:base_inventory_id>/attachments', methods=['GET', 'POST'])
def base_inventory_attachments(base_inventory_id):
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'message': '请先登录'})
    conn = get_db()
    cursor = conn.cursor()
    _ensure_attachment_tables(cursor)
    if not cursor.execute('SELECT 1 FROM base_inventory WHERE id = ?', (base_inventory_id,)).fetchone():
        return jsonify({'success': False, 'message': '基地库存记录不存在'})
    if request.method == 'GET':
        cursor.execute('SELECT id, file_name, create_time FROM base_inventory_attachments WHERE base_inventory_id = ? ORDER BY id DESC', (base_inventory_id,))
        return jsonify({'success': True, 'data': [dict(row) for row in cursor.fetchall()]})
    files = _attachment_files()
    cursor.execute('SELECT COUNT(*) FROM base_inventory_attachments WHERE base_inventory_id = ?', (base_inventory_id,))
    if len(files) + cursor.fetchone()[0] > BASE_ATTACHMENT_MAX_FILES:
        return jsonify({'success': False, 'message': f'附件最多上传{BASE_ATTACHMENT_MAX_FILES}个'})
    saved = []
    try:
        for file_storage in files:
            file_path, file_name = _save_attachment(file_storage, f'base_inventory_{base_inventory_id}')
            cursor.execute('INSERT INTO base_inventory_attachments (base_inventory_id, file_path, file_name, uploader_id, create_time) VALUES (?, ?, ?, ?, ?)', (base_inventory_id, file_path, file_name, user['id'], datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            saved.append({'id': cursor.lastrowid, 'file_name': file_name})
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return jsonify({'success': False, 'message': str(exc)})
    return jsonify({'success': True, 'data': saved})


@transfer_bp.route('/base-transfers/<string:transfer_key>/attachments', methods=['GET', 'POST'])
def base_transfer_attachments(transfer_key):
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'message': '请先登录'})
    conn = get_db()
    cursor = conn.cursor()
    _ensure_attachment_tables(cursor)
    if not cursor.execute('SELECT 1 FROM base_inventory_transfers WHERE transfer_no = ? OR batch_no = ?', (transfer_key, transfer_key)).fetchone():
        return jsonify({'success': False, 'message': '基地调拨记录不存在'})
    if request.method == 'GET':
        cursor.execute('SELECT id, file_name, create_time FROM base_transfer_attachments WHERE transfer_key = ? ORDER BY id DESC', (transfer_key,))
        return jsonify({'success': True, 'data': [dict(row) for row in cursor.fetchall()]})
    files = _attachment_files()
    saved = []
    try:
        for file_storage in files:
            file_path, file_name = _save_attachment(file_storage, f'base_transfer_{transfer_key}')
            cursor.execute('INSERT INTO base_transfer_attachments (transfer_key, file_path, file_name, uploader_id, create_time) VALUES (?, ?, ?, ?, ?)', (transfer_key, file_path, file_name, user['id'], datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            saved.append({'id': cursor.lastrowid, 'file_name': file_name})
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return jsonify({'success': False, 'message': str(exc)})
    return jsonify({'success': True, 'data': saved})


@transfer_bp.route('/base-attachments/<string:attachment_type>/<int:attachment_id>', methods=['GET', 'DELETE'])
def base_attachment_file(attachment_type, attachment_id):
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'message': '请先登录'})
    table = {'inventory': 'base_inventory_attachments', 'transfer': 'base_transfer_attachments'}.get(attachment_type)
    if not table:
        return jsonify({'success': False, 'message': '附件类型无效'})
    conn = get_db()
    cursor = conn.cursor()
    _ensure_attachment_tables(cursor)
    row = cursor.execute(f'SELECT file_path, file_name FROM {table} WHERE id = ?', (attachment_id,)).fetchone()
    if not row:
        return jsonify({'success': False, 'message': '附件不存在'})
    if request.method == 'DELETE':
        cursor.execute(f'DELETE FROM {table} WHERE id = ?', (attachment_id,))
        conn.commit()
        try:
            Path(row['file_path']).unlink(missing_ok=True)
        except OSError:
            pass
        return jsonify({'success': True, 'message': '附件已删除'})
    return send_from_directory(str(Path(row['file_path']).parent), Path(row['file_path']).name, as_attachment=False, download_name=row['file_name'])


@transfer_bp.route('/base-inventory/<int:base_inventory_id>/transfer', methods=['POST'])
def transfer_base_inventory_to_project(base_inventory_id):
    """从材料基地调拨到项目，并记录折旧价格与本次运费。"""
    user = _current_user()
    if not _can_manage_stock(user):
        return jsonify({'success': False, 'message': '无权限执行基地调拨'})

    data = request.json or {}
    try:
        project_id = int(data.get('project_id'))
        quantity = float(data.get('quantity'))
        depreciated_unit_price = float(data.get('depreciated_unit_price'))
        freight = float(data.get('freight') or 0)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '请填写有效的项目、数量、折旧后单价和运费'})
    if quantity <= 0:
        return jsonify({'success': False, 'message': '调拨数量必须大于0'})
    if depreciated_unit_price < 0 or freight < 0:
        return jsonify({'success': False, 'message': '折旧后单价和运费不能小于0'})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, project_name FROM projects WHERE id = ?", (project_id,))
    project = cursor.fetchone()
    if not project:
        return jsonify({'success': False, 'message': '目标项目不存在，请刷新后重试'})

    cursor.execute("""
        SELECT bi.*, COALESCE(m.material_name, bi.material_name) AS resolved_material_name,
               COALESCE(m.specification, bi.specification) AS resolved_specification,
               COALESCE(m.detail_spec, bi.detail_spec) AS resolved_detail_spec,
               COALESCE(u.unit_name, bi.unit_name) AS resolved_unit_name
        FROM base_inventory bi
        LEFT JOIN materials m ON bi.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        WHERE bi.id = ?
    """, (base_inventory_id,))
    inventory = cursor.fetchone()
    if not inventory:
        return jsonify({'success': False, 'message': '基地库存不存在，请刷新后重试'})
    if float(inventory['quantity'] or 0) < quantity:
        return jsonify({'success': False, 'message': '基地库存不足，无法调拨'})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    total_amount = round(quantity * depreciated_unit_price, 2)
    try:
        cursor.execute("""
            UPDATE base_inventory
            SET quantity = quantity - ?, update_time = ?
            WHERE id = ? AND quantity >= ?
        """, (quantity, now, base_inventory_id, quantity))
        if cursor.rowcount != 1:
            raise ValueError('基地库存已发生变化，请刷新后重试')
        batch_no = _generate_base_transfer_no()
        transfer_no = _generate_base_transfer_no(reserved={batch_no})
        cursor.execute("""
            INSERT INTO base_inventory_transfers (
                transfer_no, base_inventory_id, project_id,
                material_name, specification, detail_spec, unit_name,
                quantity, original_unit_price, depreciated_unit_price,
                freight, total_amount, operator_id, transfer_time, batch_no, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            transfer_no, base_inventory_id, project_id,
            inventory['resolved_material_name'], inventory['resolved_specification'],
            inventory['resolved_detail_spec'], inventory['resolved_unit_name'],
            quantity, float(inventory['unit_price'] or 0), depreciated_unit_price,
            freight, total_amount, user['id'], now, batch_no,
            escape((data.get('remark') or '').strip()),
        ))
        _copy_inventory_attachments_to_transfer(cursor, base_inventory_id, batch_no, user['id'])
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return jsonify({'success': False, 'message': str(exc)})

    return jsonify({
        'success': True,
        'message': f'已调拨到「{project["project_name"]}」',
        'transfer_no': batch_no,
        'total_amount': total_amount,
    })


@transfer_bp.route('/base-transfers/<int:transfer_id>', methods=['DELETE', 'PUT'])
def delete_or_update_transfer(transfer_id):
    """删除或编辑基地调拨记录。"""
    user = _current_user()
    if not _can_manage_stock(user):
        return jsonify({'success': False, 'message': '无权限操作基地调拨记录'})

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM base_inventory_transfers WHERE id = ?", (transfer_id,))
    transfer = cursor.fetchone()
    if not transfer:
        return jsonify({'success': False, 'message': '调拨记录不存在'})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if request.method == 'DELETE':
        try:
            cursor.execute("""
                UPDATE base_inventory
                SET quantity = quantity + ?, update_time = ?
                WHERE id = ?
            """, (transfer['quantity'], now, transfer['base_inventory_id']))
            cursor.execute("DELETE FROM base_inventory_transfers WHERE id = ?", (transfer_id,))
            conn.commit()
        except Exception as exc:
            conn.rollback()
            return jsonify({'success': False, 'message': str(exc)})
        return jsonify({
            'success': True,
            'message': f'调拨记录「{transfer["transfer_no"]}」已删除，基地库存已恢复',
        })

    # PUT: 编辑调拨记录
    data = request.json or {}
    try:
        project_id = int(data.get('project_id'))
        quantity = float(data.get('quantity'))
        depreciated_unit_price = float(data.get('depreciated_unit_price'))
        freight = float(data.get('freight') or 0)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '请填写有效的调拨信息'})
    if quantity <= 0:
        return jsonify({'success': False, 'message': '调拨数量必须大于0'})
    if depreciated_unit_price < 0 or freight < 0:
        return jsonify({'success': False, 'message': '折旧后单价和运费不能小于0'})

    cursor.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    if not cursor.fetchone():
        return jsonify({'success': False, 'message': '目标项目不存在'})

    old_quantity = float(transfer['quantity'] or 0)
    quantity_diff = quantity - old_quantity
    transfer_time = data.get('transfer_time') or transfer['transfer_time']
    total_amount = round(quantity * depreciated_unit_price, 2)
    remark = escape((data.get('remark') or '').strip())

    try:
        if quantity_diff > 0:
            cursor.execute("""
                UPDATE base_inventory
                SET quantity = quantity - ?, update_time = ?
                WHERE id = ? AND quantity >= ?
            """, (quantity_diff, now, transfer['base_inventory_id'], quantity_diff))
            if cursor.rowcount != 1:
                raise ValueError('基地库存不足，无法增加调拨数量')
        elif quantity_diff < 0:
            cursor.execute("""
                UPDATE base_inventory
                SET quantity = quantity + ?, update_time = ?
                WHERE id = ?
            """, (-quantity_diff, now, transfer['base_inventory_id']))

        cursor.execute("""
            UPDATE base_inventory_transfers
            SET project_id = ?, quantity = ?,
                depreciated_unit_price = ?, freight = ?,
                total_amount = ?, transfer_time = ?, remark = ?
            WHERE id = ?
        """, (project_id, quantity, depreciated_unit_price, freight,
              total_amount, transfer_time, remark, transfer_id))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return jsonify({'success': False, 'message': str(exc)})

    return jsonify({'success': True, 'message': '调拨记录已更新'})


@transfer_bp.route('/base-inventory/batch-transfer', methods=['POST'])
def batch_transfer_base_inventory():
    """批量调拨基地材料到项目。"""
    user = _current_user()
    if not _can_manage_stock(user):
        return jsonify({'success': False, 'message': '无权限执行基地调拨'})

    data = request.json or {}
    try:
        project_id = int(data.get('project_id'))
        freight = float(data.get('freight') or 0)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '请填写有效的项目和运费'})
    if freight < 0:
        return jsonify({'success': False, 'message': '运费不能小于0'})

    details = data.get('details') or []
    if not details:
        return jsonify({'success': False, 'message': '请至少勾选一条材料'})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, project_name FROM projects WHERE id = ?", (project_id,))
    project = cursor.fetchone()
    if not project:
        return jsonify({'success': False, 'message': '目标项目不存在'})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    results = []
    batch_no = _generate_base_transfer_no()
    reserved_nos = {batch_no}
    try:
        for index, detail in enumerate(details):
            try:
                base_inventory_id = int(detail.get('base_inventory_id'))
                quantity = float(detail.get('quantity'))
                depreciated_unit_price = float(detail.get('depreciated_unit_price'))
            except (TypeError, ValueError):
                raise ValueError('调拨明细参数无效')
            if quantity <= 0:
                raise ValueError('调拨数量必须大于0')
            if depreciated_unit_price < 0:
                raise ValueError('折旧后单价不能小于0')

            cursor.execute("""
                SELECT bi.*, COALESCE(m.material_name, bi.material_name) AS resolved_material_name,
                       COALESCE(m.specification, bi.specification) AS resolved_specification,
                       COALESCE(m.detail_spec, bi.detail_spec) AS resolved_detail_spec,
                       COALESCE(u.unit_name, bi.unit_name) AS resolved_unit_name
                FROM base_inventory bi
                LEFT JOIN materials m ON bi.material_id = m.id
                LEFT JOIN units u ON m.unit_id = u.id
                WHERE bi.id = ?
            """, (base_inventory_id,))
            inventory = cursor.fetchone()
            if not inventory:
                raise ValueError(f'基地库存记录(ID:{base_inventory_id})不存在')
            if float(inventory['quantity'] or 0) < quantity:
                raise ValueError(f'「{inventory["resolved_material_name"]}」库存不足')

            # 扣减基地库存
            cursor.execute("""
                UPDATE base_inventory
                SET quantity = quantity - ?, update_time = ?
                WHERE id = ? AND quantity >= ?
            """, (quantity, now, base_inventory_id, quantity))
            if cursor.rowcount != 1:
                raise ValueError(f'「{inventory["resolved_material_name"]}」库存已变化，请刷新后重试')

            total_amount = round(quantity * depreciated_unit_price, 2)
            transfer_no = _generate_base_transfer_no(reserved=reserved_nos)
            reserved_nos.add(transfer_no)
            row_freight = freight if index == 0 else 0
            cursor.execute("""
                INSERT INTO base_inventory_transfers (
                    transfer_no, base_inventory_id, project_id,
                    material_name, specification, detail_spec, unit_name,
                    quantity, original_unit_price, depreciated_unit_price,
                    freight, total_amount, operator_id, transfer_time, batch_no, remark
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                transfer_no, base_inventory_id, project_id,
                inventory['resolved_material_name'], inventory['resolved_specification'],
                inventory['resolved_detail_spec'], inventory['resolved_unit_name'],
                quantity, float(inventory['unit_price'] or 0), depreciated_unit_price,
                row_freight, total_amount, user['id'], now, batch_no,
                escape((data.get('remark') or '').strip()),
            ))
            _copy_inventory_attachments_to_transfer(cursor, base_inventory_id, batch_no, user['id'])
            results.append(transfer_no)

        conn.commit()
    except Exception as exc:
        conn.rollback()
        return jsonify({'success': False, 'message': str(exc)})

    return jsonify({
        'success': True,
        'message': f'已批量调拨 {len(results)} 条材料到「{project["project_name"]}」',
        'batch_no': batch_no,
        'transfer_nos': results,
    })


@transfer_bp.route('/warehouses', methods=['GET'])
def get_warehouses():
    """获取仓库/存放点及当前库存概览。"""
    if not _current_user():
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT w.id, w.warehouse_name, w.address, w.remark, w.is_default, w.create_time,
               COUNT(CASE WHEN COALESCE(i.quantity, 0) != 0 THEN 1 END) AS material_count,
               COALESCE(SUM(i.quantity), 0) AS total_quantity
        FROM warehouses w
        LEFT JOIN inventory i ON i.warehouse_id = w.id
        GROUP BY w.id
        ORDER BY w.is_default DESC, w.id ASC
    """)
    return jsonify({'success': True, 'data': [dict(row) for row in cursor.fetchall()]})


@transfer_bp.route('/warehouses', methods=['POST'])
def create_warehouse():
    """新增可复用于入库、出库和调拨的仓库/存放点。"""
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'message': '未登录'})
    if not _can_manage_stock(user):
        return jsonify({'success': False, 'message': '无权限新增存放点'})

    data = request.json or {}
    warehouse_name = (data.get('warehouse_name') or '').strip()
    if not warehouse_name:
        return jsonify({'success': False, 'message': '存放点名称不能为空'})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM warehouses WHERE warehouse_name = ?", (warehouse_name,))
    if cursor.fetchone():
        return jsonify({'success': False, 'message': '存放点名称已存在'})

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        INSERT INTO warehouses (warehouse_name, address, remark, is_default, create_time)
        VALUES (?, ?, ?, 0, ?)
    """, (
        escape(warehouse_name),
        escape((data.get('address') or '').strip()),
        escape((data.get('remark') or '').strip()),
        now,
    ))
    conn.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid})


@transfer_bp.route('/stock-transfers', methods=['GET'])
def get_stock_transfers():
    """获取调拨记录，每条材料明细单独展示一行。"""
    if not _current_user():
        return jsonify({'success': False, 'message': '未登录'})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT std.id, std.order_id, sto.transfer_no, sto.transfer_time, sto.remark,
               fw.warehouse_name AS from_warehouse_name,
               tw.warehouse_name AS to_warehouse_name,
               m.material_code, m.material_name, m.specification, u.unit_name,
               std.quantity, std.unit_price, std.amount,
               operator.real_name AS operator_name
        FROM stock_transfer_details std
        JOIN stock_transfer_orders sto ON std.order_id = sto.id
        JOIN warehouses fw ON sto.from_warehouse_id = fw.id
        JOIN warehouses tw ON sto.to_warehouse_id = tw.id
        LEFT JOIN materials m ON std.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        LEFT JOIN users operator ON sto.operator_id = operator.id
        ORDER BY sto.transfer_time DESC, sto.id DESC, std.id ASC
    """)
    return jsonify({'success': True, 'data': [dict(row) for row in cursor.fetchall()]})


@transfer_bp.route('/transfer-inventory', methods=['GET'])
def get_transfer_inventory():
    """获取调拨可用库存，不受项目筛选影响。"""
    user = _current_user()
    if not _can_manage_stock(user):
        return jsonify({'success': False, 'message': '无权限查看调拨库存'})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.material_id, i.warehouse_id, i.quantity, i.unit_price,
               m.material_code, m.material_name, m.specification,
               u.unit_name, w.warehouse_name
        FROM inventory i
        JOIN materials m ON i.material_id = m.id
        LEFT JOIN units u ON m.unit_id = u.id
        LEFT JOIN warehouses w ON i.warehouse_id = w.id
        WHERE i.quantity > 0
        ORDER BY w.is_default DESC, w.id ASC, m.material_code ASC
    """)
    return jsonify({'success': True, 'data': [dict(row) for row in cursor.fetchall()]})


@transfer_bp.route('/stock-transfers', methods=['POST'])
def create_stock_transfer():
    """创建调拨单，并原子地扣减来源库存、增加目标库存。"""
    user = _current_user()
    if not _can_manage_stock(user):
        return jsonify({'success': False, 'message': '无权限创建调拨单'})

    data = request.json or {}
    try:
        from_warehouse_id = int(data.get('from_warehouse_id'))
        to_warehouse_id = int(data.get('to_warehouse_id'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '请选择调出和调入存放点'})

    if from_warehouse_id == to_warehouse_id:
        return jsonify({'success': False, 'message': '调出和调入存放点不能相同'})

    details = data.get('details') or []
    if not details:
        return jsonify({'success': False, 'message': '请至少添加一条调拨明细'})

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM warehouses WHERE id IN (?, ?)",
            (from_warehouse_id, to_warehouse_id),
        )
        if len(cursor.fetchall()) != 2:
            raise ValueError('存放点不存在，请刷新后重试')

        transfer_no = generate_stock_transfer_no()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        transfer_time = data.get('transfer_time') or now
        cursor.execute("""
            INSERT INTO stock_transfer_orders (
                transfer_no, from_warehouse_id, to_warehouse_id,
                operator_id, transfer_time, create_time, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            transfer_no, from_warehouse_id, to_warehouse_id,
            user['id'], transfer_time, now, escape((data.get('remark') or '').strip()),
        ))
        order_id = cursor.lastrowid

        for detail in details:
            try:
                material_id = int(detail.get('material_id'))
                quantity = float(detail.get('quantity'))
            except (TypeError, ValueError):
                raise ValueError('调拨材料和数量不能为空')
            if quantity <= 0:
                raise ValueError('调拨数量必须大于0')

            cursor.execute("""
                SELECT i.quantity, i.unit_price, m.material_name
                FROM inventory i
                JOIN materials m ON i.material_id = m.id
                WHERE i.material_id = ? AND i.warehouse_id = ?
            """, (material_id, from_warehouse_id))
            inventory = cursor.fetchone()
            if not inventory or inventory['quantity'] < quantity:
                material_name = inventory['material_name'] if inventory else f'ID:{material_id}'
                current_quantity = inventory['quantity'] if inventory else 0
                raise ValueError(f'库存不足：「{material_name}」当前库存为 {current_quantity}')

            unit_price = float(inventory['unit_price'] or 0)
            cursor.execute("""
                UPDATE inventory
                SET quantity = quantity - ?, update_time = ?
                WHERE material_id = ? AND warehouse_id = ? AND quantity >= ?
            """, (quantity, now, material_id, from_warehouse_id, quantity))
            if cursor.rowcount != 1:
                raise ValueError('库存已发生变化，请刷新后重试')

            cursor.execute("""
                INSERT INTO inventory (material_id, warehouse_id, quantity, unit_price, update_time)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(material_id, warehouse_id) DO UPDATE SET
                    quantity = quantity + excluded.quantity,
                    unit_price = excluded.unit_price,
                    update_time = excluded.update_time
            """, (material_id, to_warehouse_id, quantity, unit_price, now))
            cursor.execute("""
                INSERT INTO stock_transfer_details (
                    order_id, material_id, quantity, unit_price, amount
                ) VALUES (?, ?, ?, ?, ?)
            """, (order_id, material_id, quantity, unit_price, quantity * unit_price))

        conn.commit()
        return jsonify({'success': True, 'id': order_id, 'transfer_no': transfer_no})
    except Exception as exc:
        conn.rollback()
        return jsonify({'success': False, 'message': str(exc)})
