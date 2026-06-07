"""
中文金额大写转换
"""


def amount_to_chinese(amount):
    """金额转大写"""
    if amount is None:
        amount = 0
    amount = round(float(amount), 2)
    integer_part = int(amount)
    decimal_part = round((amount - integer_part) * 100)

    chinese_digits = ['零', '壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖']
    units = ['', '拾', '佰', '仟']

    if integer_part == 0:
        result = '零'
    else:
        str_int = str(integer_part)
        length = len(str_int)

        # 按4位分组
        groups = []
        while str_int:
            groups.insert(0, str_int[-4:] if len(str_int) >= 4 else str_int)
            str_int = str_int[:-4]

        group_units = ['', '万', '亿', '万亿']
        result = ''

        for gi, group in enumerate(groups):
            group_str = ''
            group_len = len(group)

            for i, digit in enumerate(group):
                d = int(digit)
                pos = group_len - 1 - i  # 0=个位, 1=十位, 2=百位, 3=千位

                if d != 0:
                    # 前面有0且不是组首，加零
                    if i > 0 and group[i-1] == '0' and not group_str.endswith('零'):
                        group_str += '零'
                    group_str += chinese_digits[d] + units[pos]
                # 组内末尾的0不加零，由下一级处理

            if group_str:
                result += group_str + group_units[len(groups) - 1 - gi]
            elif result and not result.endswith('零') and gi < len(groups) - 1:
                # 当前组全0，但后面还有组，需要加零（如果还没加的话）
                # 这里先不加，等遇到非零时再加
                pass

        # 处理跨组的零：如果结果中有"万"或"亿"后面紧跟数字（不是零开头），需要检查
        result = result.rstrip('零')

    if decimal_part == 0:
        return f"{result}元整"
    else:
        jiao = decimal_part // 10
        fen = decimal_part % 10
        result += '元'
        if jiao > 0:
            result += chinese_digits[jiao] + '角'
        elif fen > 0:
            result += '零'
        if fen > 0:
            result += chinese_digits[fen] + '分'
        return result


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
