"""Additive schema for auditable matching, without rewriting old inquiries."""


def init_inquiry_price_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inquiry_price_match_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            current_key TEXT NOT NULL, history_key TEXT NOT NULL,
            current_description TEXT NOT NULL, history_description TEXT NOT NULL,
            confirmed_by INTEGER NOT NULL, confirmed_name TEXT NOT NULL,
            reason TEXT NOT NULL, created_at TEXT NOT NULL,
            revoked_at TEXT, revoked_by INTEGER
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_inquiry_price_match_keys
        ON inquiry_price_match_rules(current_key, history_key, revoked_at)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inquiry_price_material_snapshots (
            item_id INTEGER PRIMARY KEY, inquiry_id INTEGER NOT NULL,
            description TEXT NOT NULL, created_at TEXT NOT NULL
        )
    """)
