"""Comparable historical deal prices for inquiry detail views."""


def add_historical_lowest_prices(cursor, inquiry, rows):
    material_ids = sorted({row['material_id'] for row in rows if row.get('material_id')})
    if not material_ids or not inquiry:
        return

    date = inquiry.get('inquiry_date') or (inquiry.get('create_time') or '')[:10]
    placeholders = ','.join('?' for _ in material_ids)
    cursor.execute(f"""
        WITH past_inquiries AS (
            SELECT id
            FROM purchase_inquiries
            WHERE approval_status = '已同意'
              AND id <> ?
              AND (
                  COALESCE(NULLIF(inquiry_date, ''), SUBSTR(create_time, 1, 10), '') < ?
                  OR (
                      COALESCE(NULLIF(inquiry_date, ''), SUBSTR(create_time, 1, 10), '') = ?
                      AND id < ?
                  )
              )
        ), deals AS (
            SELECT item.material_id,
                   COALESCE(NULLIF(TRIM(item.detail_spec), ''), '常规') AS detail_spec,
                   COALESCE(item.is_cash_price, 0) AS is_cash_price,
                   quote.tax_price AS price
            FROM purchase_inquiry_items item
            JOIN past_inquiries history ON history.id = item.inquiry_id
            JOIN purchase_inquiry_quotes quote ON quote.id = (
                SELECT candidate.id
                FROM purchase_inquiry_quotes candidate
                WHERE candidate.item_id = item.id
                  AND (candidate.is_selected = 1 OR candidate.is_lowest = 1)
                ORDER BY CASE WHEN candidate.is_selected = 1 THEN 0 ELSE 1 END, candidate.id
                LIMIT 1
            )
            WHERE item.material_id IN ({placeholders}) AND quote.tax_price > 0

            UNION ALL

            SELECT detail.material_id,
                   COALESCE(NULLIF(TRIM(material.detail_spec), ''), '常规') AS detail_spec,
                   0 AS is_cash_price,
                   detail.this_price AS price
            FROM purchase_inquiry_details detail
            JOIN past_inquiries history ON history.id = detail.inquiry_id
            LEFT JOIN materials material ON material.id = detail.material_id
            WHERE detail.material_id IN ({placeholders}) AND detail.this_price > 0
              AND NOT EXISTS (
                  SELECT 1 FROM purchase_inquiry_items item
                  WHERE item.inquiry_id = detail.inquiry_id
              )
        )
        SELECT material_id, detail_spec, is_cash_price, MIN(price) AS lowest_price
        FROM deals
        GROUP BY material_id, detail_spec, is_cash_price
    """, (inquiry['id'], date, date, inquiry['id'], *material_ids, *material_ids))
    prices = {
        (row['material_id'], row['detail_spec'], row['is_cash_price']): row['lowest_price']
        for row in cursor.fetchall()
    }
    for row in rows:
        key = (
            row.get('material_id'),
            (row.get('detail_spec') or '').strip() or '常规',
            row.get('is_cash_price') or 0,
        )
        row['historical_lowest_price'] = prices.get(key)
