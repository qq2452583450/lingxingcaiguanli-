"""
材料调拨 API 测试
"""


def login_as_material_clerk(client):
    with client.session_transaction() as session:
        session['user'] = {
            'id': 1,
            'username': 'clerk',
            'real_name': '测试材料员',
            'role_name': '材料员',
        }


def login_as_base_owner(client):
    with client.session_transaction() as session:
        session['user'] = {
            'id': 1,
            'username': 'base_owner',
            'real_name': '测试基地负责人',
            'role_name': '基地负责人',
        }


def seed_transfer_inventory(test_db):
    cursor = test_db.cursor()
    cursor.execute("INSERT INTO units (unit_name) VALUES ('件')")
    unit_id = cursor.lastrowid
    cursor.execute("""
        INSERT INTO materials (material_code, material_name, specification, unit_id)
        VALUES ('MAT-001', '测试材料', '标准件', ?)
    """, (unit_id,))
    material_id = cursor.lastrowid
    cursor.execute("INSERT INTO warehouses (warehouse_name, is_default) VALUES ('材料基地', 1)")
    from_warehouse_id = cursor.lastrowid
    cursor.execute("INSERT INTO warehouses (warehouse_name, is_default) VALUES ('项目仓库', 0)")
    to_warehouse_id = cursor.lastrowid
    cursor.execute("""
        INSERT INTO inventory (material_id, warehouse_id, quantity, unit_price)
        VALUES (?, ?, 100, 12.5)
    """, (material_id, from_warehouse_id))
    test_db.commit()
    return material_id, from_warehouse_id, to_warehouse_id


def test_create_transfer_moves_inventory_atomically(client, test_db):
    login_as_material_clerk(client)
    material_id, from_warehouse_id, to_warehouse_id = seed_transfer_inventory(test_db)

    response = client.post('/api/stock-transfers', json={
        'from_warehouse_id': from_warehouse_id,
        'to_warehouse_id': to_warehouse_id,
        'details': [{'material_id': material_id, 'quantity': 35}],
        'remark': '基地调往项目',
    })
    data = response.get_json()

    assert data['success'] is True
    assert data['transfer_no'].startswith('DB-')
    rows = test_db.execute("""
        SELECT warehouse_id, quantity, unit_price
        FROM inventory
        WHERE material_id = ?
        ORDER BY warehouse_id
    """, (material_id,)).fetchall()
    assert [(row['warehouse_id'], row['quantity'], row['unit_price']) for row in rows] == [
        (from_warehouse_id, 65, 12.5),
        (to_warehouse_id, 35, 12.5),
    ]


def test_base_owner_can_view_base_inventory(client, test_db):
    login_as_base_owner(client)
    seed_transfer_inventory(test_db)

    response = client.get('/api/base-inventory')
    data = response.get_json()

    assert data['success'] is True


def test_transfer_rolls_back_when_inventory_is_insufficient(client, test_db):
    login_as_material_clerk(client)
    material_id, from_warehouse_id, to_warehouse_id = seed_transfer_inventory(test_db)

    response = client.post('/api/stock-transfers', json={
        'from_warehouse_id': from_warehouse_id,
        'to_warehouse_id': to_warehouse_id,
        'details': [{'material_id': material_id, 'quantity': 101}],
    })
    data = response.get_json()

    assert data['success'] is False
    assert '库存不足' in data['message']
    assert test_db.execute("SELECT COUNT(*) FROM stock_transfer_orders").fetchone()[0] == 0
    assert test_db.execute("SELECT quantity FROM inventory WHERE material_id = ?", (material_id,)).fetchone()[0] == 100


def test_stock_out_uses_selected_warehouse(client, test_db):
    login_as_material_clerk(client)
    material_id, from_warehouse_id, to_warehouse_id = seed_transfer_inventory(test_db)
    test_db.execute("""
        INSERT INTO inventory (material_id, warehouse_id, quantity, unit_price)
        VALUES (?, ?, 20, 12.5)
    """, (material_id, to_warehouse_id))
    test_db.commit()

    response = client.post('/api/stock-out', json={
        'warehouse_id': to_warehouse_id,
        'team_name': '测试班组',
        'receiver_name': '测试领用人',
        'details': [{'material_id': material_id, 'quantity': 5, 'unit_price': 12.5}],
    })
    data = response.get_json()

    assert data['success'] is True
    source_quantity = test_db.execute("""
        SELECT quantity FROM inventory WHERE material_id = ? AND warehouse_id = ?
    """, (material_id, from_warehouse_id)).fetchone()[0]
    target_quantity = test_db.execute("""
        SELECT quantity FROM inventory WHERE material_id = ? AND warehouse_id = ?
    """, (material_id, to_warehouse_id)).fetchone()[0]
    order_warehouse_id = test_db.execute("SELECT warehouse_id FROM stock_out_orders").fetchone()[0]
    assert source_quantity == 100
    assert target_quantity == 15
    assert order_warehouse_id == to_warehouse_id


def test_base_inventory_manual_stock_in_creates_standalone_base_material(client, test_db):
    login_as_material_clerk(client)
    material_count = test_db.execute("SELECT COUNT(*) FROM materials").fetchone()[0]

    response = client.post('/api/base-inventory', json={
        'material_name': '基地旧材料',
        'specification': 'DN50',
        'detail_spec': '镀锌钢管 6米',
        'unit_name': '根',
        'quantity': 8,
        'unit_price': 13.5,
        'remark': '旧料盘点补录',
    })
    data = response.get_json()

    assert data['success'] is True
    base_inventory = test_db.execute("""
        SELECT material_id, material_name, specification, detail_spec, unit_name, quantity, unit_price, remark
        FROM base_inventory
    """).fetchone()
    assert test_db.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == material_count
    assert base_inventory['material_id'] is None
    assert base_inventory['material_name'] == '基地旧材料'
    assert base_inventory['specification'] == 'DN50'
    assert base_inventory['detail_spec'] == '镀锌钢管 6米'
    assert base_inventory['unit_name'] == '根'
    assert base_inventory['quantity'] == 8
    assert base_inventory['unit_price'] == 13.5
    assert base_inventory['remark'] == '旧料盘点补录'

    listed = client.get('/api/base-inventory').get_json()['data'][0]
    assert listed['material_code'] == '基地自有'
    assert listed['material_name'] == '基地旧材料'
    assert listed['specification'] == 'DN50'
    assert listed['detail_spec'] == '镀锌钢管 6米'
    assert listed['remark'] == '旧料盘点补录'


def test_base_inventory_quick_stock_in_moves_project_inventory(client, test_db):
    login_as_material_clerk(client)
    material_id, project_warehouse_id, _ = seed_transfer_inventory(test_db)

    response = client.post('/api/base-inventory', json={
        'material_id': material_id,
        'quantity': 8,
        'unit_price': 13.5,
        'source_warehouse_id': project_warehouse_id,
    })
    data = response.get_json()

    assert data['success'] is True
    assert test_db.execute("""
        SELECT quantity FROM inventory WHERE material_id = ? AND warehouse_id = ?
    """, (material_id, project_warehouse_id)).fetchone()[0] == 92
    assert test_db.execute("""
        SELECT quantity FROM base_inventory WHERE material_id = ?
    """, (material_id,)).fetchone()[0] == 8


def test_base_inventory_list_only_returns_explicitly_stocked_materials(client, test_db):
    login_as_material_clerk(client)
    material_id, _, other_warehouse_id = seed_transfer_inventory(test_db)
    test_db.execute("""
        INSERT INTO inventory (material_id, warehouse_id, quantity, unit_price)
        VALUES (?, ?, 20, 99)
    """, (material_id, other_warehouse_id))
    test_db.execute("""
        INSERT INTO base_inventory (material_id, quantity, unit_price)
        VALUES (?, 6, 13.5)
    """, (material_id,))
    test_db.commit()

    response = client.get('/api/base-inventory')
    data = response.get_json()

    assert data['success'] is True
    assert data['warehouse_name'] == '材料基地'
    assert len(data['data']) == 1
    assert data['data'][0]['quantity'] == 6
    assert data['data'][0]['unit_price'] == 13.5


def test_base_inventory_transfer_to_project_records_depreciation_and_freight(client, test_db):
    login_as_material_clerk(client)
    test_db.execute("""
        INSERT INTO projects (project_code, project_name)
        VALUES ('XM-001', '测试项目')
    """)
    project_id = test_db.execute("SELECT id FROM projects").fetchone()[0]
    test_db.execute("""
        INSERT INTO base_inventory (
            material_name, specification, detail_spec, unit_name, quantity, unit_price
        ) VALUES ('基地旧材料', 'DN50', '镀锌钢管 6米', '根', 10, 100)
    """)
    base_inventory_id = test_db.execute("SELECT id FROM base_inventory").fetchone()[0]
    test_db.commit()

    response = client.post(f'/api/base-inventory/{base_inventory_id}/transfer', json={
        'project_id': project_id,
        'quantity': 3,
        'depreciated_unit_price': 75,
        'freight': 30,
        'remark': '调拨到现场',
    })
    data = response.get_json()

    assert data['success'] is True
    assert data['transfer_no'].startswith('JDB-')
    assert data['total_amount'] == 225
    assert test_db.execute("SELECT quantity FROM base_inventory").fetchone()[0] == 7
    transfer = test_db.execute("""
        SELECT transfer_no, project_id, material_name, quantity, original_unit_price,
               depreciated_unit_price, freight, total_amount, batch_no, remark
        FROM base_inventory_transfers
    """).fetchone()
    assert transfer['project_id'] == project_id
    assert transfer['material_name'] == '基地旧材料'
    assert transfer['quantity'] == 3
    assert transfer['original_unit_price'] == 100
    assert transfer['depreciated_unit_price'] == 75
    assert transfer['freight'] == 30
    assert transfer['total_amount'] == 225
    assert transfer['batch_no'] == data['transfer_no']
    assert transfer['transfer_no'] != data['transfer_no']
    assert transfer['remark'] == '调拨到现场'

    listed = client.get('/api/base-transfers').get_json()['data'][0]
    assert listed['project_name'] == '测试项目'
    assert listed['total_amount'] == 225


def test_update_base_inventory_transfer_adjusts_base_stock(client, test_db):
    login_as_material_clerk(client)
    test_db.execute("""
        INSERT INTO projects (project_code, project_name)
        VALUES ('XM-EDIT', 'edit project')
    """)
    project_id = test_db.execute("SELECT id FROM projects WHERE project_code = 'XM-EDIT'").fetchone()[0]
    test_db.execute("""
        INSERT INTO base_inventory (
            material_name, specification, unit_name, quantity, unit_price
        ) VALUES ('base material', 'DN50', 'pcs', 10, 100)
    """)
    base_inventory_id = test_db.execute("SELECT last_insert_rowid()").fetchone()[0]
    test_db.commit()

    create_response = client.post(f'/api/base-inventory/{base_inventory_id}/transfer', json={
        'project_id': project_id,
        'quantity': 3,
        'depreciated_unit_price': 75,
        'freight': 30,
        'remark': 'created',
    })
    assert create_response.get_json()['success'] is True
    transfer_id = test_db.execute("SELECT id FROM base_inventory_transfers").fetchone()[0]

    response = client.put(f'/api/base-transfers/{transfer_id}', json={
        'project_id': project_id,
        'quantity': 5,
        'depreciated_unit_price': 60,
        'freight': 15,
        'transfer_time': '2026-06-04 10:30:00',
        'remark': 'edited',
    })
    data = response.get_json()

    assert data['success'] is True
    assert test_db.execute("SELECT quantity FROM base_inventory").fetchone()[0] == 5
    transfer = test_db.execute("""
        SELECT quantity, depreciated_unit_price, freight, total_amount, transfer_time, remark
        FROM base_inventory_transfers
        WHERE id = ?
    """, (transfer_id,)).fetchone()
    assert transfer['quantity'] == 5
    assert transfer['depreciated_unit_price'] == 60
    assert transfer['freight'] == 15
    assert transfer['total_amount'] == 300
    assert transfer['transfer_time'] == '2026-06-04 10:30:00'
    assert transfer['remark'] == 'edited'


def test_batch_base_inventory_transfer_uses_one_batch_no(client, test_db):
    login_as_material_clerk(client)
    test_db.execute("""
        INSERT INTO projects (project_code, project_name)
        VALUES ('XM-001', '测试项目')
    """)
    project_id = test_db.execute("SELECT id FROM projects").fetchone()[0]
    test_db.execute("""
        INSERT INTO base_inventory (
            material_name, specification, unit_name, quantity, unit_price
        ) VALUES ('基地旧材料A', 'DN50', '根', 10, 100)
    """)
    first_id = test_db.execute("SELECT last_insert_rowid()").fetchone()[0]
    test_db.execute("""
        INSERT INTO base_inventory (
            material_name, specification, unit_name, quantity, unit_price
        ) VALUES ('基地旧材料B', 'DN20', '根', 8, 80)
    """)
    second_id = test_db.execute("SELECT last_insert_rowid()").fetchone()[0]
    test_db.commit()

    response = client.post('/api/base-inventory/batch-transfer', json={
        'project_id': project_id,
        'freight': 10,
        'remark': '同一批调拨',
        'details': [
            {'base_inventory_id': first_id, 'quantity': 2, 'depreciated_unit_price': 70},
            {'base_inventory_id': second_id, 'quantity': 3, 'depreciated_unit_price': 60},
        ],
    })
    data = response.get_json()

    assert data['success'] is True
    assert data['batch_no'] != data['transfer_nos'][0]
    rows = test_db.execute("""
        SELECT transfer_no, batch_no, freight, total_amount, remark
        FROM base_inventory_transfers
        ORDER BY id
    """).fetchall()
    assert len(rows) == 2
    assert rows[0]['transfer_no'] != rows[1]['transfer_no']
    assert rows[0]['batch_no'] != rows[0]['transfer_no']
    assert rows[0]['batch_no'] == rows[1]['batch_no'] == data['batch_no']
    assert [row['freight'] for row in rows] == [10, 0]
    assert [row['total_amount'] for row in rows] == [140, 180]
    assert rows[0]['remark'] == rows[1]['remark'] == '同一批调拨'
