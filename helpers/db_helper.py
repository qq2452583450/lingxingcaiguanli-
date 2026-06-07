"""
数据库连接辅助函数 — 使用 Flask g 缓存，teardown 自动关闭
"""
import sqlite3
from flask import g
import config


def get_db():
    """获取数据库连接（Flask g 缓存，请求结束自动关闭）"""
    if 'db' not in g:
        g.db = sqlite3.connect(config.DATABASE_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.text_factory = str
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(exception=None):
    """关闭数据库连接（注册为 teardown_appcontext 回调）"""
    db = g.pop('db', None)
    if db is not None:
        db.close()
