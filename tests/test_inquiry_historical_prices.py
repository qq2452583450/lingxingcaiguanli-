import pytest


@pytest.fixture
def price_context(client, test_db):
    cursor = test_db.cursor()
    cursor.execute("INSERT INTO roles (role_name) VALUES ('系统管理员')")
    role_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO users (username, password, role_id) VALUES ('price_admin', 'x', ?)",
        (role_id,),
    )
    user_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO materials (material_code, material_name, detail_spec) VALUES ('PRICE-1', '测试材料', '常规')"
    )
    material_id = cursor.lastrowid
    cursor.execute("INSERT INTO suppliers (supplier_name) VALUES ('测试供应商')")
    supplier_id = cursor.lastrowid
    with client.session_transaction() as session:
        session['user'] = {'id': user_id, 'username': 'price_admin'}

    def inquiry(number, date='2026-10-01', status='已同意'):
        cursor.execute(
            "INSERT INTO purchase_inquiries (inquiry_no, inquiry_date, approval_status, applicant_id) VALUES (?, ?, ?, ?)",
            (number, date, status, user_id),
        )
        return cursor.lastrowid

    def item(inquiry_id, price, *, detail_spec='常规', cash=0, selected=1, lowest=0, material=None):
        cursor.execute(
            "INSERT INTO purchase_inquiry_items (inquiry_id, material_id, detail_spec, is_cash_price, library_price) VALUES (?, ?, ?, ?, 20)",
            (inquiry_id, material or material_id, detail_spec, cash),
        )
        item_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO purchase_inquiry_quotes (item_id, supplier_id, tax_price, is_selected, is_lowest) VALUES (?, ?, ?, ?, ?)",
            (item_id, supplier_id, price, selected, lowest),
        )
        return item_id

    return cursor, material_id, supplier_id, inquiry, item


def test_detail_historical_price_uses_only_previous_approved_comparable_deals(client, test_db, price_context):
    cursor, material_id, supplier_id, inquiry, item = price_context
    item(inquiry('OLD-12'), 12)
    selected_item = item(inquiry('OLD-8'), 8)
    cursor.execute(
        "INSERT INTO purchase_inquiry_quotes (item_id, supplier_id, tax_price, is_lowest) VALUES (?, ?, 3, 1)",
        (selected_item, supplier_id),
    )
    item(inquiry('DRAFT', status='草稿'), 1)
    item(inquiry('PENDING', status='待审批'), 1)
    item(inquiry('OTHER-SPEC'), 2, detail_spec='不同尺寸')
    item(inquiry('CASH'), 2, cash=1)
    item(inquiry('ZERO'), 0)
    item(inquiry('FUTURE', date='2026-10-09'), 1)
    cursor.execute("INSERT INTO materials (material_code, material_name) VALUES ('PRICE-2', '测试材料')")
    other_material_id = cursor.lastrowid
    item(inquiry('OTHER-MATERIAL'), 1, material=other_material_id)
    current_id = inquiry('CURRENT', date='2026-10-07', status='草稿')
    item(current_id, 0.5)
    item(current_id, 10, detail_spec='没有历史成交')
    item(current_id, 10, cash=1)
    item(inquiry('LATER-SAME-DAY', date='2026-10-07'), 1)
    test_db.commit()

    response = client.get(f'/api/purchase-inquiries/{current_id}')
    assert response.status_code == 200
    rows = response.get_json()['items']
    assert rows[0]['historical_lowest_price'] == 8
    assert rows[1]['historical_lowest_price'] is None
    assert rows[2]['historical_lowest_price'] == 2


def test_historical_price_falls_back_to_lowest_flag_when_no_selected_quote(client, test_db, price_context):
    cursor, material_id, supplier_id, inquiry, item = price_context
    old_item = item(inquiry('LOWEST-FALLBACK'), 0.3456, selected=0, lowest=1)
    cursor.execute(
        "INSERT INTO purchase_inquiry_quotes (item_id, supplier_id, tax_price) VALUES (?, ?, 0.1)",
        (old_item, supplier_id),
    )
    current_id = inquiry('FALLBACK-CURRENT', date='2026-10-07', status='草稿')
    item(current_id, 1)
    test_db.commit()

    assert client.get(f'/api/purchase-inquiries/{current_id}').get_json()['items'][0]['historical_lowest_price'] == 0.3456


def test_historical_prices_support_legacy_details_without_counting_duplicate_legacy_rows(client, test_db, price_context):
    cursor, material_id, supplier_id, inquiry, item = price_context
    old_id = inquiry('LEGACY-OLD')
    cursor.execute(
        "INSERT INTO purchase_inquiry_details (inquiry_id, material_id, supplier_id, this_price) VALUES (?, ?, ?, 7)",
        (old_id, material_id, supplier_id),
    )
    modern_id = inquiry('MODERN-WITH-LEGACY-COPY')
    item(modern_id, 9)
    cursor.execute(
        "INSERT INTO purchase_inquiry_details (inquiry_id, material_id, supplier_id, this_price) VALUES (?, ?, ?, 1)",
        (modern_id, material_id, supplier_id),
    )
    current_id = inquiry('LEGACY-CURRENT', date='2026-10-07', status='草稿')
    cursor.execute(
        "INSERT INTO purchase_inquiry_details (inquiry_id, material_id, supplier_id, this_price) VALUES (?, ?, ?, 2)",
        (current_id, material_id, supplier_id),
    )
    test_db.commit()

    data = client.get(f'/api/purchase-inquiries/{current_id}').get_json()
    assert data['legacy'] is True
    assert data['details'][0]['historical_lowest_price'] == 7


def test_supplier_does_not_receive_other_suppliers_historical_deal_prices(client, test_db, price_context):
    cursor, material_id, supplier_id, inquiry, item = price_context
    item(inquiry('PRIVATE-OLD'), 8)
    current_id = inquiry('SUPPLIER-CURRENT', date='2026-10-07', status='草稿')
    item(current_id, 10)
    cursor.execute("INSERT INTO roles (role_name) VALUES ('供应商')")
    cursor.execute("INSERT INTO users (username, password, role_id) VALUES ('price_supplier', 'x', ?)", (cursor.lastrowid,))
    supplier_user = cursor.lastrowid
    cursor.execute('UPDATE suppliers SET user_id=? WHERE id=?', (supplier_user, supplier_id))
    test_db.commit()
    with client.session_transaction() as session:
        session['user'] = {'id': supplier_user, 'username': 'price_supplier'}

    row = client.get(f'/api/purchase-inquiries/{current_id}').get_json()['items'][0]
    assert row.get('historical_lowest_price') is None


@pytest.mark.parametrize('legacy', [False, True])
def test_approval_print_shows_comparable_historical_price_after_library_price(
    client, test_db, price_context, tmp_path, legacy
):
    cursor, material_id, supplier_id, inquiry, item = price_context
    item(inquiry('PRINT-OLD'), 8.3456)
    item(inquiry('PRINT-OTHER-SPEC'), 1, detail_spec='不同尺寸')
    item(inquiry('PRINT-CASH-OLD'), 5.6789, cash=1)
    current_id = inquiry('PRINT-CURRENT', date='2026-10-07', status='草稿')
    if legacy:
        cursor.execute(
            "INSERT INTO purchase_inquiry_details (inquiry_id, material_id, supplier_id, this_price, library_price) VALUES (?, ?, ?, 10, 20)",
            (current_id, material_id, supplier_id),
        )
    else:
        item(current_id, 10)
        item(current_id, 10, cash=1)
        item(current_id, 10, detail_spec='没有历史成交')
    test_db.commit()

    response = client.get(f'/api/purchase-inquiries/{current_id}/approval-print')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    (tmp_path / 'approval-print.html').write_text(html, encoding='utf-8')
    assert html.index('库内价</th>') < html.index('历史最低价</th>') < html.index('class="supplier-col"')
    assert '<td class="num historical-price">¥8.3456</td>' in html
    if not legacy:
        assert '<td class="num historical-price">¥5.6789</td>' in html
        assert '<td class="num historical-price">—</td>' in html


def test_approval_print_does_not_expose_historical_prices_to_suppliers(client, test_db, price_context):
    cursor, material_id, supplier_id, inquiry, item = price_context
    item(inquiry('PRINT-PRIVATE-OLD'), 8.3456)
    current_id = inquiry('PRINT-SUPPLIER-CURRENT', date='2026-10-07', status='草稿')
    item(current_id, 10)
    cursor.execute("INSERT INTO roles (role_name) VALUES ('供应商')")
    cursor.execute("INSERT INTO users (username, password, role_id) VALUES ('print_supplier', 'x', ?)", (cursor.lastrowid,))
    supplier_user = cursor.lastrowid
    test_db.commit()
    with client.session_transaction() as session:
        session['user'] = {'id': supplier_user, 'username': 'print_supplier'}

    html = client.get(f'/api/purchase-inquiries/{current_id}/approval-print').get_data(as_text=True)
    assert '¥8.3456' not in html
    assert '<td class="num historical-price">—</td>' in html
