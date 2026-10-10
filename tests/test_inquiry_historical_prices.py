import pytest

from services.inquiry_price_service import _comparable_detail_spec, _parameter_profile, capture_inquiry_price_snapshots


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
    cursor.execute("INSERT INTO units (unit_name) VALUES ('米')")
    cursor.execute(
        "INSERT INTO materials (material_code, material_name, detail_spec, unit_id) VALUES ('PRICE-1', '测试材料', '常规', ?)",
        (cursor.lastrowid,),
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


@pytest.mark.parametrize('current_spec', ['300×3', '300 × 3', '３００＊３', '300x3', '300X3'])
def test_historical_price_matches_equivalent_dimension_notation(client, test_db, price_context, current_spec):
    cursor, material_id, supplier_id, inquiry, item = price_context
    item(inquiry('OLD-STAR'), 29, detail_spec='300*3')
    item(inquiry('OLD-TIMES'), 30, detail_spec='300×3')
    item(inquiry('OTHER-THICKNESS'), 1, detail_spec='300×2.5')
    item(inquiry('OTHER-QUALIFIER'), 2, detail_spec='300×3 双面焊')
    item(inquiry('OTHER-CASH'), 3, detail_spec='300*3', cash=1)
    cursor.execute("INSERT INTO materials (material_code, material_name) VALUES ('OTHER-REGION', '测试材料')")
    item(inquiry('OTHER-REGION'), 4, detail_spec='300*3', material=cursor.lastrowid)
    current_id = inquiry('NOTATION-CURRENT', date='2026-10-07', status='草稿')
    item(current_id, 30.55, detail_spec=current_spec)
    test_db.commit()

    row = client.get(f'/api/purchase-inquiries/{current_id}').get_json()['items'][0]
    assert row['historical_lowest_price'] == 29


def test_approval_print_matches_equivalent_dimension_notation(client, test_db, price_context):
    cursor, material_id, supplier_id, inquiry, item = price_context
    item(inquiry('PRINT-STAR-OLD'), 29, detail_spec='300*3')
    current_id = inquiry('PRINT-TIMES-CURRENT', date='2026-10-07', status='草稿')
    item(current_id, 30.55, detail_spec='300×3')
    test_db.commit()
    html = client.get(f'/api/purchase-inquiries/{current_id}/approval-print').get_data(as_text=True)
    assert '<td class="num historical-price">¥29.00</td>' in html
    assert '等价规格匹配；PRINT-STAR-OLD' not in html
    assert '历史价格来源与口径' not in html


@pytest.mark.parametrize('a,b,name', [
    ('30cm×3mm', '300×3', '止水钢板'),
    ('0.3m×3mm', '300×3', '止水钢板'),
    ('Φ14 × 墙厚25cm × 总长60cm', 'Φ14×墙厚250mm×总长600mm', '止水螺杆'),
])
def test_explicit_length_units_are_equivalent(a, b, name):
    assert _comparable_detail_spec(a, name) == _comparable_detail_spec(b, name)


def test_electrical_model_leading_zero_is_not_erased():
    assert _comparable_detail_spec('ABC001', '电缆') != _comparable_detail_spec('ABC1', '电缆')


@pytest.mark.parametrize('a,b,name', [
    ('宽300mm×厚3mm 双面焊', '300×3 双面焊', '止水钢板'),
    ('厚3mm 宽30cm 双面焊', '300×3 双面焊', '止水钢板'),
    ('直径14mm 墙厚25cm 总长60cm', 'Φ14×墙厚250mm×总长600mm', '止水螺杆'),
    ('L=900mm 管壁厚2.5mm 钢板厚3mm', '长900mm 钢管壁厚2.5mm 钢板厚度3mm', '人防密闭套管'),
])
def test_key_parameters_preserve_meaning_and_normalize_labeled_format(a, b, name):
    assert _parameter_profile(a, name) == _parameter_profile(b, name)


def test_key_parameters_do_not_drop_welding_or_length_requirements():
    assert _parameter_profile('300×3 双面焊', '止水钢板') != _parameter_profile('300×3', '止水钢板')
    assert _parameter_profile('3000×300×3', '止水钢板') != _parameter_profile('300×3', '止水钢板')


def test_candidate_confirmation_is_audited_reusable_and_revocable(client, test_db, price_context):
    cursor, material_id, supplier_id, inquiry, item = price_context
    item(inquiry('OLD-PARTIAL'), 35, detail_spec='直角')
    current_id = inquiry('REVIEW-CURRENT', date='2026-10-07', status='草稿')
    current_item = item(current_id, 38.8, detail_spec='300*3 双面焊')
    test_db.commit()
    url = f'/api/purchase-inquiries/{current_id}/price-history/{current_item}'
    result = client.get(url).get_json()
    row = result['data']
    assert result['can_confirm'] is True
    assert row['historical_lowest_price'] is None
    assert len(row['historical_price_candidates']) == 1
    payload = {'action': 'confirm', 'current_key': row['historical_price_current_key'],
               'history_key': row['historical_price_candidates'][0]['history_key'], 'reason': '已核对原单，同规格双面焊'}
    assert client.post(url, json={**payload, 'reason': ''}).status_code == 400
    assert client.post(url, json=payload).status_code == 200
    assert client.post(url, json=payload).status_code == 409
    row = client.get(url).get_json()['data']
    assert row['historical_lowest_price'] == 35
    source = row['historical_price_source']
    assert source['match_type'] == '人工确认匹配'
    assert source['confirmed_name'] == 'price_admin'
    assert source['confirmation_reason'] == payload['reason']
    assert client.get(f'/api/purchase-inquiries/{current_id}').get_json()['items'][0]['historical_lowest_price'] == 35
    # New inquiries reuse only the same material/parameter combination.
    future_id = inquiry('REUSE-CURRENT', date='2026-10-08', status='草稿')
    future_item = item(future_id, 38.8, detail_spec='300 × 3 双面焊')
    test_db.commit()
    assert client.get(f'/api/purchase-inquiries/{future_id}/price-history/{future_item}').get_json()['data']['historical_lowest_price'] == 35
    assert client.post(url, json={**payload, 'action': 'revoke'}).status_code == 200
    assert client.get(url).get_json()['data']['historical_lowest_price'] is None
    audit = test_db.cursor().execute('SELECT * FROM inquiry_price_match_rules').fetchone()
    assert audit['revoked_at'] and audit['revoked_by']


def test_price_review_requires_login_and_get_does_not_create_rules(client, test_db, price_context):
    cursor, material_id, supplier_id, inquiry, item = price_context
    item(inquiry('READ-ONLY-OLD'), 29)
    current_id = inquiry('READ-ONLY-CURRENT', date='2026-10-07', status='草稿')
    current_item = item(current_id, 30)
    test_db.commit()
    url = f'/api/purchase-inquiries/{current_id}/price-history/{current_item}'
    assert client.get(url).status_code == 200
    assert test_db.cursor().execute('SELECT COUNT(*) FROM inquiry_price_match_rules').fetchone()[0] == 0
    assert test_db.cursor().execute('SELECT COUNT(*) FROM inquiry_price_material_snapshots').fetchone()[0] == 0
    with client.session_transaction() as session:
        session.clear()
    assert client.get(url).status_code == 401
    assert client.post(url, json={}).status_code == 401


def test_confirm_does_not_accept_stale_or_incompatible_spec(client, test_db, price_context):
    cursor, material_id, supplier_id, inquiry, item = price_context
    item(inquiry('THINNER'), 1, detail_spec='300×2.5')
    item(inquiry('PARTIAL'), 35, detail_spec='直角')
    current_id = inquiry('STALE-CURRENT', date='2026-10-07', status='草稿')
    current_item = item(current_id, 38.8, detail_spec='300×3 双面焊')
    test_db.commit()
    url = f'/api/purchase-inquiries/{current_id}/price-history/{current_item}'
    row = client.get(url).get_json()['data']
    assert len(row['historical_price_candidates']) == 1
    payload = {'action': 'confirm', 'current_key': row['historical_price_current_key'],
               'history_key': row['historical_price_candidates'][0]['history_key'], 'reason': '核对'}
    assert client.post(url, json={**payload, 'history_key': 'forged'}).status_code == 400
    cursor.execute('UPDATE purchase_inquiry_items SET detail_spec=? WHERE id=?', ('300×4 双面焊', current_item))
    test_db.commit()
    assert client.post(url, json=payload).status_code == 409


@pytest.mark.parametrize('role,can_read,can_confirm', [
    ('材料员', True, False), ('材料审批负责人', True, True), ('供应商', False, False),
])
def test_price_review_permissions(client, test_db, price_context, role, can_read, can_confirm):
    cursor, material_id, supplier_id, inquiry, item = price_context
    item(inquiry('OLD-REVIEW'), 35, detail_spec='直角')
    current_id = inquiry('PERMISSION-CURRENT', date='2026-10-07', status='草稿')
    current_item = item(current_id, 38.8, detail_spec='300×3 双面焊')
    cursor.execute('INSERT INTO roles (role_name) VALUES (?)', (role,))
    cursor.execute("INSERT INTO users (username, password, role_id) VALUES ('review_actor', 'x', ?)", (cursor.lastrowid,))
    user_id = cursor.lastrowid
    test_db.commit()
    with client.session_transaction() as session:
        session['user'] = {'id': user_id, 'username': 'review_actor'}
    url = f'/api/purchase-inquiries/{current_id}/price-history/{current_item}'
    response = client.get(url)
    assert response.status_code == (200 if can_read else 403)
    if can_read:
        row = response.get_json()['data']
        payload = {'action': 'confirm', 'current_key': row['historical_price_current_key'],
                   'history_key': row['historical_price_candidates'][0]['history_key'], 'reason': '核对原始采购单'}
    else:
        payload = {}
    assert client.post(url, json=payload).status_code == (200 if can_confirm else 403)


def test_cross_region_and_unit_history_is_never_a_candidate(client, test_db, price_context):
    cursor, material_id, supplier_id, inquiry, item = price_context
    unit_id = cursor.execute("SELECT id FROM units WHERE unit_name='米'").fetchone()[0]
    cursor.execute("UPDATE materials SET material_code='KMLX00001', unit_id=? WHERE id=?", (unit_id, material_id))
    for code, unit in [('KMLX00002', unit_id), ('QJLX00001', unit_id), ('KMLX00003', None)]:
        cursor.execute("INSERT INTO materials (material_code, material_name, unit_id) VALUES (?, '测试材料', ?)", (code, unit))
        other_id = cursor.lastrowid
        item(inquiry(code), 1, detail_spec='300*3', material=other_id)
    current_id = inquiry('REGION-CURRENT', date='2026-10-07', status='草稿')
    current_item = item(current_id, 30, detail_spec='300×3')
    test_db.commit()
    row = client.get(f'/api/purchase-inquiries/{current_id}/price-history/{current_item}').get_json()['data']
    assert row['historical_lowest_price'] is None
    assert [h['material_code'] for h in row['historical_price_candidates']] == ['KMLX00002']


def test_approved_snapshot_prevents_later_master_spec_changes(client, test_db, price_context):
    cursor, material_id, supplier_id, inquiry, item = price_context
    cursor.execute("UPDATE materials SET specification='300×3' WHERE id=?", (material_id,))
    old_id = inquiry('SNAPSHOT-OLD')
    item(old_id, 29, detail_spec='300×3')
    capture_inquiry_price_snapshots(cursor, old_id, '2026-10-01')
    cursor.execute("UPDATE materials SET specification='300×4' WHERE id=?", (material_id,))
    current_id = inquiry('SNAPSHOT-CURRENT', date='2026-10-07', status='草稿')
    current_item = item(current_id, 30, detail_spec='300×4')
    test_db.commit()
    row = client.get(f'/api/purchase-inquiries/{current_id}/price-history/{current_item}').get_json()['data']
    assert row['historical_lowest_price'] is None
    assert row['historical_price_candidates'] == []


def test_positive_fallback_and_cash_only_reason(client, test_db, price_context):
    cursor, material_id, supplier_id, inquiry, item = price_context
    old_item = item(inquiry('ZERO-SELECTED'), 0, selected=1)
    cursor.execute('INSERT INTO purchase_inquiry_quotes (item_id, supplier_id, tax_price, is_lowest) VALUES (?, ?, 7, 1)', (old_item, supplier_id))
    item(inquiry('ONLY-CASH'), 5, detail_spec='现金独有规格', cash=1)
    current_id = inquiry('FALLBACK-REASON-CURRENT', date='2026-10-07', status='草稿')
    item(current_id, 9)
    current_item = item(current_id, 9, detail_spec='现金独有规格')
    test_db.commit()
    row = client.get(f'/api/purchase-inquiries/{current_id}').get_json()['items'][0]
    assert row['historical_lowest_price'] == 7
    assert row['historical_price_source']['price_basis'] == '最低报价回退'
    row = client.get(f'/api/purchase-inquiries/{current_id}/price-history/{current_item}').get_json()['data']
    assert row['historical_lowest_price'] is None
    assert '现金价口径' in row['historical_price_reason'] or row['historical_price_candidates']


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


@pytest.mark.parametrize('rate,label', [(0.13, '税率 13%'), (0.01, '税率 1%'),
                                     (0, '税率 0%'), (0.015, '税率 1.5%'),
                                     (None, '税率未记录')])
@pytest.mark.parametrize('legacy', [False, True])
def test_display_tax_rate_uses_quote_with_library_reference(client, test_db, price_context, rate, label, legacy):
    cursor, material_id, supplier_id, inquiry, item = price_context
    current_id = inquiry('TAX-PRINT', status='草稿')
    item_id = item(current_id, 10)
    cursor.execute('UPDATE suppliers SET tax_rate=0.09 WHERE id=?', (supplier_id,))
    cursor.execute('UPDATE purchase_inquiry_quotes SET tax_rate=? WHERE item_id=?', (rate, item_id))
    if legacy:
        cursor.execute('DELETE FROM purchase_inquiry_quotes WHERE item_id=?', (item_id,))
        cursor.execute('DELETE FROM purchase_inquiry_items WHERE id=?', (item_id,))
        cursor.execute('INSERT INTO purchase_inquiry_details (inquiry_id, material_id, supplier_id, this_price) VALUES (?, ?, ?, 10)', (current_id, material_id, supplier_id))
    test_db.commit()
    data = client.get(f'/api/purchase-inquiries/{current_id}').get_json()
    quote = data['details'][0] if legacy else data['items'][0]['quotes'][0]
    assert quote.get('tax_rate') == (None if legacy else rate)
    assert quote['supplier_tax_rate'] == 0.09
    html = client.get(f'/api/purchase-inquiries/{current_id}/approval-print').get_data(as_text=True)
    expected = '税率未记录' if legacy else label
    assert f'<span class="quote-tax-rate">本次{expected}；供应商库税率 9%' in html
    assert ('（参考）' if legacy or rate is None else '（不一致）') in html


def test_print_keeps_material_quote_rates_for_same_supplier(client, test_db, price_context):
    cursor, _, supplier_id, inquiry, item = price_context
    current_id = inquiry('MIXED-TAX', status='草稿')
    first = item(current_id, 10)
    second = item(current_id, 20)
    cursor.execute('UPDATE purchase_inquiry_quotes SET tax_rate=0.13 WHERE item_id=?', (first,))
    cursor.execute('UPDATE purchase_inquiry_quotes SET tax_rate=0.01 WHERE item_id=?', (second,))
    cursor.execute('UPDATE suppliers SET tax_rate=0.03 WHERE id=?', (supplier_id,))
    test_db.commit()
    html = client.get(f'/api/purchase-inquiries/{current_id}/approval-print').get_data(as_text=True)
    assert '<span class="quote-tax-rate">本次税率 13%；供应商库税率 3%（不一致）</span>' in html
    assert '<span class="quote-tax-rate">本次税率 1%；供应商库税率 3%（不一致）</span>' in html


@pytest.mark.parametrize('stored,rate,expected', [
    (7.25, 0.13, '7.25'), (None, 0.13, '8.85'),
    (0, 0.13, '8.85'), (None, 0, '10.00'),
    (None, None, '—'), (None, -1, '—'),
])
def test_signature_sheet_untaxed_price_and_no_provenance(client, test_db, price_context, stored, rate, expected):
    cursor, _, supplier_id, inquiry, item = price_context
    current = inquiry('PRINT-UNTAXED', status='草稿')
    item_id = item(current, 10)
    cursor.execute('UPDATE suppliers SET tax_rate=0.09 WHERE id=?', (supplier_id,))
    cursor.execute('UPDATE purchase_inquiry_quotes SET tax_exempt_price=?, tax_rate=? WHERE item_id=?', (stored, rate, item_id))
    test_db.commit()
    response = client.get(f'/api/purchase-inquiries/{current}/approval-print')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f'<span class="quote-untaxed-price">未税 {expected}</span>' in html
    assert '<span class="quote-unit-price">含税 10.00</span>' in html
    assert '历史价格来源与口径' not in html
    assert '确认人：' not in html
    assert '历史最低价</th>' in html


def test_many_supplier_signature_sheet_layout(client, test_db, price_context, tmp_path):
    cursor, _, supplier_id, inquiry, item = price_context
    current = inquiry('多供应商签字单排版测试', status='草稿')
    item_id = item(current, 10)
    cursor.execute('UPDATE purchase_inquiry_quotes SET tax_rate=0.13, tax_exempt_price=8.85 WHERE item_id=?', (item_id,))
    for i in range(7):
        cursor.execute('INSERT INTO suppliers (supplier_name, tax_rate) VALUES (?, 0.13)', (f'测试供应商{i + 2}建筑材料有限公司',))
        cursor.execute('INSERT INTO purchase_inquiry_quotes (item_id, supplier_id, tax_price, tax_exempt_price, tax_rate) VALUES (?, ?, 10, 8.85, 0.13)', (item_id, cursor.lastrowid))
    test_db.commit()
    response = client.get(f'/api/purchase-inquiries/{current}/approval-print')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<table class="many-suppliers">' in html
    assert html.count('<span class="quote-untaxed-price">未税 8.85</span>') == 8
    (tmp_path / 'signature-sheet.html').write_text(html, encoding='utf-8')
