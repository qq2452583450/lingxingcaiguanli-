"""
输入清理 — 对外部输入做基础清理，防止恶意数据入库
规则：移除 HTML 标签（非转义），保留原始文本
"""
import re

_TAG_RE = re.compile(r'<[^>]*>')


def sanitize(value):
    """移除字符串中的 HTML 标签，返回纯文本"""
    if not isinstance(value, str):
        return value
    return _TAG_RE.sub('', value)


def sanitize_dict(data, *fields):
    """对字典中的指定字段做 sanitize，不修改原 dict"""
    result = dict(data)
    for field in fields:
        if field in result and isinstance(result[field], str):
            result[field] = sanitize(result[field])
    return result
