"""Backfill only missing modern inquiry nominations, with backup and audit."""
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from helpers.inquiry_nomination import lowest_priced_quote

FIX_ID = '2026-10-07-default-missing-inquiry-nominations'


def repair(conn):
    conn.row_factory = sqlite3.Row
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS inquiry_nomination_repairs
                        (id TEXT PRIMARY KEY, applied_at TEXT NOT NULL, result_json TEXT NOT NULL)''')
        previous = conn.execute('SELECT result_json FROM inquiry_nomination_repairs WHERE id=?', (FIX_ID,)).fetchone()
        if previous:
            conn.rollback()
            return {'status': 'skipped', 'previous_result': json.loads(previous[0])}
        changes = []
        items = conn.execute('''SELECT i.*, p.inquiry_no, p.selected_supplier_id
            FROM purchase_inquiry_items i JOIN purchase_inquiries p ON p.id=i.inquiry_id
            WHERE COALESCE(i.selected_quote_id,0)=0
              AND NOT EXISTS (SELECT 1 FROM purchase_inquiry_quotes q
                              WHERE q.item_id=i.id AND q.is_selected=1)
            ORDER BY i.id''').fetchall()
        for item in items:
            quotes = [dict(q) for q in conn.execute('SELECT * FROM purchase_inquiry_quotes WHERE item_id=? ORDER BY id', (item['id'],))]
            # A whole-order manual nomination must never be replaced by another supplier.
            if item['selected_supplier_id']:
                quotes = [q for q in quotes if q['supplier_id'] == item['selected_supplier_id']]
            selected = lowest_priced_quote(quotes)
            if not selected:
                continue
            conn.execute('UPDATE purchase_inquiry_items SET selected_quote_id=? WHERE id=?', (selected['supplier_id'], item['id']))
            conn.execute('UPDATE purchase_inquiry_quotes SET is_selected=1 WHERE id=?', (selected['id'],))
            changes.append({'inquiry_id': item['inquiry_id'], 'inquiry_no': item['inquiry_no'],
                            'item_id': item['id'], 'quote_id': selected['id'],
                            'supplier_id': selected['supplier_id'], 'tax_price': selected['tax_price'],
                            'quantity': item['quantity']})
        totals = []
        freight_exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='purchase_inquiry_supplier_freights'").fetchone()
        for inquiry_id in sorted({c['inquiry_id'] for c in changes}):
            header = conn.execute('SELECT inquiry_no,total_amount FROM purchase_inquiries WHERE id=?', (inquiry_id,)).fetchone()
            selected_rows = conn.execute('''SELECT i.quantity,i.library_price,q.tax_price,q.supplier_id
                FROM purchase_inquiry_items i JOIN purchase_inquiry_quotes q
                  ON q.id=(SELECT qq.id FROM purchase_inquiry_quotes qq WHERE qq.item_id=i.id
                    AND (qq.is_selected=1 OR qq.supplier_id=i.selected_quote_id)
                    ORDER BY qq.is_selected DESC,qq.id LIMIT 1)
                WHERE i.inquiry_id=?''', (inquiry_id,)).fetchall()
            goods = sum(float(r['quantity'] or 0) * float(r['tax_price'] or 0) for r in selected_rows)
            suppliers = {r['supplier_id'] for r in selected_rows}
            freight = 0
            if freight_exists:
                freight = sum(float(r['tax_freight'] or 0) for r in conn.execute(
                    'SELECT supplier_id,tax_freight FROM purchase_inquiry_supplier_freights WHERE inquiry_id=?', (inquiry_id,))
                    if r['supplier_id'] in suppliers)
            total = round(goods + freight, 2)
            below = int(any(float(r['library_price'] or 0) > float(r['tax_price'] or 0) > 0 for r in selected_rows))
            conn.execute('UPDATE purchase_inquiries SET total_amount=?,is_below_library_price=? WHERE id=?', (total, below, inquiry_id))
            totals.append({'inquiry_no': header['inquiry_no'], 'old_total': header['total_amount'], 'new_total': total, 'freight': freight})
        result = {'status': 'applied', 'selected_items': len(changes), 'affected_inquiries': len(totals), 'changes': changes, 'totals': totals}
        conn.execute('INSERT INTO inquiry_nomination_repairs VALUES (?,?,?)',
                     (FIX_ID, datetime.now().isoformat(), json.dumps(result, ensure_ascii=False)))
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=config.DATABASE_PATH)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    path = Path(args.db).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    with sqlite3.connect(str(path), timeout=60) as conn:
        if args.apply:
            backup = path.parent / 'backups' / (path.name + '.before-default-nominations-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
            backup.parent.mkdir(exist_ok=True)
            with sqlite3.connect(str(backup)) as dest:
                conn.backup(dest)
            print('backup=' + str(backup))
            result = repair(conn)
        else:
            # Inspect the exact repair on an in-memory copy; production stays unchanged.
            with sqlite3.connect(':memory:') as preview:
                conn.backup(preview)
                result = repair(preview)
            result['status'] = 'preview'
        # Detailed business records stay in the private database audit, not public CI logs.
        applied = result.get('previous_result', result)
        print(json.dumps({'status': result['status'], 'selected_items': applied['selected_items'],
                          'affected_inquiries': applied['affected_inquiries']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
