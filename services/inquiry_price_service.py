"""Conservative, traceable historical tax-inclusive deal price matching."""

import hashlib
import json
import re
import unicodedata
from decimal import Decimal

from helpers.material_regions import get_region_name


def _comparable_detail_spec(value, material_name=''):
    text = unicodedata.normalize('NFKC', value or '').strip() or '常规'
    text = re.sub(r'\s+', '', text)
    text = re.sub(r'(?<=\d)[*xX×](?=\d)', '×', text)
    # Explicit lengths only; never infer electrical model or package units.
    if any(word in material_name for word in ('钢板', '螺杆', '套管', '接线盒')):
        text = re.sub(r'(\d+(?:\.\d+)?)(cm|mm|m)(?![a-zA-Z])',
                      lambda m: format(Decimal(m[1]) * {'cm': 10, 'mm': 1, 'm': 1000}[m[2].lower()], 'f'),
                      text, flags=re.I)
        text = re.sub(r'\d+(?:\.\d+)?', lambda m: format(Decimal(m[0]).normalize(), 'f'), text)
    return text


def _unit(value):
    text = (value or '').strip()
    return {'m': '米', 'pcs': '个'}.get(text, text)


def _description(row):
    return {key: row.get(key) or '' for key in (
        'material_id', 'material_name', 'material_code', 'specification',
        'detail_spec', 'brand', 'unit_name', 'is_cash_price',
    )}


def _key(description):
    # Equivalent notation can reuse a rule; changed dimensions/qualifiers cannot.
    normalized = dict(description)
    for field in ('specification', 'detail_spec'):
        normalized[field] = _parameter_profile(description[field], description['material_name'])
    normalized['unit_name'] = _unit(description['unit_name'])
    if _generic(description['brand']):
        normalized['brand'] = ''
    return hashlib.sha256(json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _generic(value):
    return (value or '').strip() in ('', '-', '/', '无', '通用', '常规')


def _parameter_profile(value, name):
    """Extract labeled parameters conservatively, retaining unparsed qualifiers."""
    text = _comparable_detail_spec(value, name)
    parameters = {}
    patterns = {}
    if '钢板' in name:
        patterns = {'宽度': r'宽(?:度)?[:=]?(\d+(?:\.\d+)?)',
                    '厚度': r'厚(?:度)?[:=]?(\d+(?:\.\d+)?)',
                    '长度': r'(?:长度|长|L)[:=]?(\d+(?:\.\d+)?)'}
        chain = re.search(r'\d+(?:\.\d+)?(?:×\d+(?:\.\d+)?){1,2}', text)
        if chain:
            values = chain[0].split('×')
            fields = ('宽度', '厚度') if len(values) == 2 else ('长度', '宽度', '厚度')
            parameters.update(zip(fields, values))
            text = text[:chain.start()] + text[chain.end():]
    elif '螺杆' in name:
        patterns = {'直径': r'(?:Φ|φ|直径)[:=]?(\d+(?:\.\d+)?)',
                    '墙厚': r'墙厚[:=]?(\d+(?:\.\d+)?)',
                    '总长': r'总长[:=]?(\d+(?:\.\d+)?)'}
    elif '套管' in name:
        patterns = {'长度': r'(?:长度|长|L)[:=]?(\d+(?:\.\d+)?)',
                    '管径': r'(?:Φ|φ|管径|DN)[:=]?(\d+(?:\.\d+)?)',
                    '钢管壁厚': r'(?:钢管壁厚|管壁厚)[:=]?(\d+(?:\.\d+)?)',
                    '钢板厚度': r'(?:钢板厚度|钢板厚)[:=]?(\d+(?:\.\d+)?)'}
    for label, pattern in patterns.items():
        matches = list(re.finditer(pattern, text))
        if len(matches) == 1:
            parameters[label] = matches[0][1]
            text = re.sub(pattern, '', text)
    # Only separators between recognized fields are formatting, not qualifiers.
    if parameters:
        text = text.strip('×,:;；，')
        text = re.sub(r'[×,:;；，]+', '', text)
    return parameters, text


def _eligible(current, history):
    """Hard boundaries cannot be overridden by a confirmation."""
    if current['material_name'] != history['material_name']:
        return False
    if not _unit(current['unit_name']) or _unit(current['unit_name']) != _unit(history['unit_name']):
        return False
    if bool(current['is_cash_price']) != bool(history['is_cash_price']):
        return False
    region = get_region_name(current['material_code'])
    other_region = get_region_name(history['material_code'])
    if region and other_region and region != other_region:
        return False
    if current['material_id'] != history['material_id']:
        if not region or region != other_region:
            return False
    if not _generic(current['brand']) and not _generic(history['brand']) and current['brand'] != history['brand']:
        return False
    name = current['material_name']
    for field in ('specification', 'detail_spec'):
        a = _comparable_detail_spec(current[field], name)
        b = _comparable_detail_spec(history[field], name)
        numbers_a = re.findall(r'\d+(?:\.\d+)?', a)
        numbers_b = re.findall(r'\d+(?:\.\d+)?', b)
        parameters_a, _ = _parameter_profile(a, name)
        parameters_b, _ = _parameter_profile(b, name)
        if any(parameters_a[k] != parameters_b[k] for k in parameters_a.keys() & parameters_b.keys()):
            return False
        fully_labeled = (len(parameters_a) == len(numbers_a) and len(parameters_b) == len(numbers_b)
                         and parameters_a and parameters_b)
        if not fully_labeled and numbers_a and numbers_b and numbers_a != numbers_b:
            return False
        for opposite in (('阴角', '阳角'), ('单面焊', '双面焊'), ('铜', '铝')):
            if any(x in a and y in b for x, y in (opposite, opposite[::-1])):
                return False
    return True


def _automatic_match(current, history):
    if current['material_id'] != history['material_id']:
        return None
    if current['brand'] != history['brand'] and not (_generic(current['brand']) and _generic(history['brand'])):
        return None
    fields = ('specification', 'detail_spec')
    if all((current[f] or '').strip() == (history[f] or '').strip() for f in fields):
        return '精确匹配'
    name = current['material_name']
    if all(_parameter_profile(current[f], name) == _parameter_profile(history[f], name) for f in fields):
        return '等价规格匹配'
    return None


def _has_table(cursor, name):
    return cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def capture_inquiry_price_snapshots(cursor, inquiry_id, now):
    """Capture approved item identity in the approval transaction, never on GET."""
    cursor.execute("""
        SELECT i.*, m.material_name, m.material_code, m.specification, u.unit_name
        FROM purchase_inquiry_items i JOIN materials m ON m.id=i.material_id
        LEFT JOIN units u ON u.id=m.unit_id WHERE i.inquiry_id=?
    """, (inquiry_id,))
    for row in cursor.fetchall():
        cursor.execute("""
            INSERT OR REPLACE INTO inquiry_price_material_snapshots
            (item_id, inquiry_id, description, created_at) VALUES (?, ?, ?, ?)
        """, (row['id'], inquiry_id, json.dumps(_description(dict(row)), ensure_ascii=False), now))


def add_historical_lowest_prices(cursor, inquiry, rows, legacy=False):
    if not rows or not inquiry:
        return
    ids = sorted({row['material_id'] for row in rows if row.get('material_id')})
    if not ids:
        return
    marks = ','.join('?' for _ in ids)
    cursor.execute(f"""
        SELECT m.*, u.unit_name FROM materials m LEFT JOIN units u ON u.id=m.unit_id
        WHERE m.material_name IN (SELECT material_name FROM materials WHERE id IN ({marks}))
    """, ids)
    materials = {r['id']: dict(r) for r in cursor.fetchall()}
    current_snapshots = {}
    if not legacy and _has_table(cursor, 'inquiry_price_material_snapshots'):
        cursor.execute('SELECT item_id, description FROM inquiry_price_material_snapshots WHERE inquiry_id=?', (inquiry['id'],))
        current_snapshots = {r['item_id']: json.loads(r['description']) for r in cursor.fetchall()}
    for row in rows:
        row['_price_description'] = current_snapshots.get(row.get('id')) or _description({**materials.get(row.get('material_id'), {}), **row})
    history_ids = list(materials)
    if not history_ids:
        for row in rows:
            row.pop('_price_description', None)
            row['historical_lowest_price'] = None
        return
    history_marks = ','.join('?' for _ in history_ids)
    date = inquiry.get('inquiry_date') or (inquiry.get('create_time') or '')[:10]
    cursor.execute(f"""
        WITH past_inquiries AS (
            SELECT p.*, COALESCE(pr.project_name, pr.project_code, '') AS project_name
            FROM purchase_inquiries p LEFT JOIN projects pr ON pr.id=p.project_id
            WHERE p.approval_status='已同意' AND p.id<>?
            AND (COALESCE(NULLIF(p.inquiry_date,''), SUBSTR(p.create_time,1,10),'')<?
                OR (COALESCE(NULLIF(p.inquiry_date,''), SUBSTR(p.create_time,1,10),'')=? AND p.id<?))
        )
        SELECT i.id AS item_id, i.material_id, i.detail_spec, i.brand, i.is_cash_price,
               p.id AS inquiry_id, p.inquiry_no, p.inquiry_date, p.approve_time, p.project_name,
               q.id AS quote_id, q.tax_price AS price, q.tax_rate, s.supplier_name,
               CASE WHEN q.is_selected=1 THEN '拟定成交价' ELSE '最低报价回退' END AS price_basis,
               'modern' AS record_type
        FROM purchase_inquiry_items i JOIN past_inquiries p ON p.id=i.inquiry_id
        JOIN purchase_inquiry_quotes q ON q.id=(
            SELECT c.id FROM purchase_inquiry_quotes c WHERE c.item_id=i.id
            AND c.tax_price>0 AND (c.is_selected=1 OR c.is_lowest=1)
            ORDER BY CASE WHEN c.is_selected=1 THEN 0 ELSE 1 END, c.id LIMIT 1)
        LEFT JOIN suppliers s ON s.id=q.supplier_id
        WHERE i.material_id IN ({history_marks})
        UNION ALL
        SELECT d.id, d.material_id, m.detail_spec, m.brand, 0,
               p.id, p.inquiry_no, p.inquiry_date, p.approve_time, p.project_name,
               NULL, d.this_price, NULL, s.supplier_name, '旧版审批采购价', 'legacy'
        FROM purchase_inquiry_details d JOIN past_inquiries p ON p.id=d.inquiry_id
        JOIN materials m ON m.id=d.material_id LEFT JOIN suppliers s ON s.id=d.supplier_id
        WHERE d.material_id IN ({history_marks}) AND d.this_price>0
          AND NOT EXISTS (SELECT 1 FROM purchase_inquiry_items i WHERE i.inquiry_id=d.inquiry_id)
    """, (inquiry['id'], date, date, inquiry['id'], *history_ids, *history_ids))
    history_rows = [dict(r) for r in cursor.fetchall()]
    snapshots = {}
    if _has_table(cursor, 'inquiry_price_material_snapshots'):
        snapshot_ids = [h['item_id'] for h in history_rows if h['record_type'] == 'modern']
        if snapshot_ids:
            cursor.execute(f"SELECT item_id, description FROM inquiry_price_material_snapshots WHERE item_id IN ({','.join('?' for _ in snapshot_ids)})", snapshot_ids)
            snapshots = {r['item_id']: json.loads(r['description']) for r in cursor.fetchall()}
    rules = {}
    if _has_table(cursor, 'inquiry_price_match_rules'):
        current_keys = [_key(row['_price_description']) for row in rows]
        cursor.execute(f"SELECT * FROM inquiry_price_match_rules WHERE revoked_at IS NULL AND current_key IN ({','.join('?' for _ in current_keys)}) ORDER BY id", current_keys)
        rules = {(r['current_key'], r['history_key']): dict(r) for r in cursor.fetchall()}
    for row in rows:
        current = row.pop('_price_description')
        current_key = _key(current)
        matches, candidates = [], []
        cash_only = False
        for history in history_rows:
            description = snapshots.get(history['item_id']) if history['record_type'] == 'modern' else None
            source = description or _description({**materials.get(history['material_id'], {}), **history})
            if (bool(source['is_cash_price']) != bool(current['is_cash_price'])
                    and _eligible(current, {**source, 'is_cash_price': current['is_cash_price']})):
                cash_only = True
            if not _eligible(current, source):
                continue
            key = _key(source)
            rule = rules.get((current_key, key))
            match_type = _automatic_match(current, source) or ('人工确认匹配' if rule else None)
            evidence = {**history, **source, 'history_key': key, 'match_type': match_type or '待确认',
                        'key_parameters': _parameter_profile(source['detail_spec'], source['material_name'])[0],
                        'parameter_source': '审批时规格快照' if description else '旧记录（部分参数来自材料档案）',
                        'rule_id': rule['id'] if rule else None,
                        'confirmed_name': rule['confirmed_name'] if rule else '',
                        'confirmation_reason': rule['reason'] if rule else ''}
            (matches if match_type else candidates).append(evidence)
        matches.sort(key=lambda h: (h['price'], -(h['inquiry_id'] or 0)))
        candidates.sort(key=lambda h: (h['price'], -(h['inquiry_id'] or 0)))
        row['historical_lowest_price'] = matches[0]['price'] if matches else None
        row['historical_price_source'] = matches[0] if matches else None
        row['historical_price_matches'] = matches
        row['historical_price_candidates'] = candidates
        row['historical_price_reason'] = ('计价单位未记录，无法比较历史单价' if not current['unit_name'] else
            '已匹配历史审批含税单价' if matches else
            '规格参数不足或描述不同，待确认' if candidates else
            '仅有另一种现金价口径记录' if cash_only else '无可比历史审批成交记录')
        row['historical_price_item_id'] = row.get('id')
        row['historical_price_inquiry_id'] = inquiry['id']
        row['historical_price_legacy'] = legacy
        row['historical_price_current_key'] = current_key
        row['historical_price_current_description'] = current
        row['historical_price_key_parameters'] = _parameter_profile(current['detail_spec'], current['material_name'])[0]
