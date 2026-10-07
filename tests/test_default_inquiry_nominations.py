import sqlite3
from pathlib import Path

from helpers.inquiry_nomination import default_item_nominations
from tools.default_missing_inquiry_nominations import repair


def test_deployment_backfills_before_service_start():
    source = Path('deploy/deploy.ps1').read_text(encoding='utf-8')
    assert source.count('tools\\default_missing_inquiry_nominations.py') == 2
    assert source.index('tools\\default_missing_inquiry_nominations.py') < source.index('Start-Service -Name $ServiceName')


def test_default_uses_ex_tax_price_and_preserves_manual_choice():
    quotes = [
        {'supplier_id': 1, 'tax_price': 0, 'is_lowest': 1},
        {'supplier_id': 2, 'tax_price': 110, 'tax_exempt_price': 100},
        {'supplier_id': 3, 'tax_price': 113, 'tax_exempt_price': 99},
    ]
    items = [{'quotes': quotes}, {'quotes': quotes, 'selected_quote_id': 2}, {'quotes': []}]
    default_item_nominations(items)
    assert items[0]['selected_quote_id'] == 3
    assert items[1]['selected_quote_id'] == 2
    assert 'selected_quote_id' not in items[2]
    default_item_nominations(items)
    assert items[0]['selected_quote_id'] == 3


def test_existing_selected_flag_is_preserved():
    items = [{'quotes': [{'supplier_id': 1, 'tax_price': 2},
                         {'supplier_id': 2, 'tax_price': 4, 'is_selected': 1}]}]
    default_item_nominations(items)
    assert items[0]['selected_quote_id'] == 2


def test_backfill_totals_freight_preserves_other_data_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    conn.executescript('''
        CREATE TABLE purchase_inquiries(id INTEGER PRIMARY KEY,inquiry_no TEXT,
            selected_supplier_id INTEGER,total_amount REAL,is_below_library_price INTEGER,approval_status TEXT);
        CREATE TABLE purchase_inquiry_items(id INTEGER PRIMARY KEY,inquiry_id INTEGER,
            quantity REAL,library_price REAL,selected_quote_id INTEGER);
        CREATE TABLE purchase_inquiry_quotes(id INTEGER PRIMARY KEY,item_id INTEGER,supplier_id INTEGER,
            tax_price REAL,tax_exempt_price REAL,tax_rate REAL,is_selected INTEGER,is_lowest INTEGER);
        CREATE TABLE purchase_inquiry_supplier_freights(inquiry_id INTEGER,supplier_id INTEGER,tax_freight REAL);
        INSERT INTO purchase_inquiries VALUES(1,'PARTIAL',NULL,40,0,'已同意'),(2,'EMPTY',NULL,0,0,'已同意'),
            (3,'MANUAL',8,0,0,'草稿');
        INSERT INTO purchase_inquiry_items VALUES(1,1,2,25,7),(2,1,3,25,NULL),(3,2,10,50,NULL),
            (4,2,1,50,NULL),(5,3,1,50,NULL),(6,1,2,25,NULL);
        INSERT INTO purchase_inquiry_quotes VALUES(1,1,7,20,18,0.13,1,0),(2,1,8,10,9,0.13,0,1),
            (3,2,8,12,10,0.13,0,0),(4,2,7,11,10.9,0.01,0,1),
            (5,3,7,2,1.9,0.01,0,1),(6,4,7,0,0,0.01,0,0),
            (7,5,7,1,0.9,0.13,0,1),(8,5,8,2,1.9,0.01,0,0),
            (9,6,7,4,3.9,0.01,1,0);
        INSERT INTO purchase_inquiry_supplier_freights VALUES(1,7,5),(1,8,10),(2,7,5);
    ''')
    original_prices = conn.execute('SELECT id,tax_price FROM purchase_inquiry_quotes').fetchall()
    result = repair(conn)
    assert result['selected_items'] == 3
    assert result['affected_inquiries'] == 3
    assert conn.execute('SELECT selected_quote_id FROM purchase_inquiry_items WHERE id=2').fetchone()[0] == 8
    assert conn.execute('SELECT selected_quote_id FROM purchase_inquiry_items WHERE id=4').fetchone()[0] is None
    assert conn.execute('SELECT selected_quote_id FROM purchase_inquiry_items WHERE id=5').fetchone()[0] == 8
    assert conn.execute('SELECT selected_quote_id FROM purchase_inquiry_items WHERE id=6').fetchone()[0] is None
    assert conn.execute('SELECT total_amount FROM purchase_inquiries WHERE id=1').fetchone()[0] == 99
    assert conn.execute('SELECT total_amount FROM purchase_inquiries WHERE id=2').fetchone()[0] == 25
    assert conn.execute('SELECT approval_status FROM purchase_inquiries WHERE id=1').fetchone()[0] == '已同意'
    assert [tuple(r) for r in conn.execute('SELECT id,tax_price FROM purchase_inquiry_quotes')] == original_prices
    assert repair(conn)['status'] == 'skipped'
