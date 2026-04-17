"""
日期帮助工具
"""
from datetime import datetime, timedelta


def get_now():
    """获取当前时间字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_today():
    """获取当前日期字符串"""
    return datetime.now().strftime("%Y-%m-%d")


def format_date(date_str, fmt_from="%Y-%m-%d %H:%M:%S", fmt_to="%Y-%m-%d"):
    """格式化日期字符串"""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, fmt_from)
        return dt.strftime(fmt_to)
    except:
        return date_str


def get_date_for_order():
    """获取用于单号的日期部分 YYMMDD"""
    return datetime.now().strftime("%y%m%d")


def get_period_string():
    """获取对账单周期字符串，如 2026.1.1~2026.1.15"""
    return ""
