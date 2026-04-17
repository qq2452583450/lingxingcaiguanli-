"""
中文金额大写转换
"""


def number_to_chinese_currency(amount: float) -> str:
    """
    数字金额转换为中文大写

    参数:
        amount: 金额数字，如 546.00

    返回:
        中文大写金额字符串，如 伍佰肆拾陆元整
    """
    # 整数部分
    integer_part = int(amount)
    # 小数部分（保留2位）
    decimal_part = round((amount - integer_part) * 100)

    # 数字到中文大写映射
    units = ["仟", "佰", "拾", ""]
    digits = ["零", "壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖"]

    if integer_part == 0:
        result = "零元"
    else:
        result = ""
        int_str = str(integer_part)
        length = len(int_str)

        for i, digit_char in enumerate(int_str):
            digit = int(digit_char)
            unit_idx = length - i - 1
            if digit != 0:
                result += digits[digit] + units[min(unit_idx, 3)]
            else:
                if i == 0 or result[-1] == "零":
                    continue
                result += "零"

        # 移除末尾的零
        result = result.rstrip("零")
        result += "元"

    # 处理小数部分
    if decimal_part == 0:
        result += "整"
    else:
        if decimal_part >= 10:
            d0 = decimal_part // 10
            d1 = decimal_part % 10
            if d0 != 0:
                result += digits[d0] + "角"
            if d1 != 0:
                result += digits[d1] + "分"
        elif decimal_part >= 1:
            result += digits[decimal_part] + "角"
        else:
            result += "整"

    return result
