"""金额工具：Decimal 规范化与中文大写金额。"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
_DIGITS = "零壹贰叁肆伍陆柒捌玖"
_UNITS = ["", "拾", "佰", "仟"]
_SECTIONS = ["", "万", "亿", "万亿"]


def to_decimal(value) -> Decimal | None:
    """把 '¥1,234.50'、'1234.5'、'***'（免税）之类转成两位小数的 Decimal；无法识别返回 None。"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value.quantize(CENT, ROUND_HALF_UP)
    if isinstance(value, (int, float)):
        return Decimal(str(value)).quantize(CENT, ROUND_HALF_UP)
    s = str(value).strip()
    if not s:
        return None
    if re.fullmatch(r"\*+|免税|不征税", s):
        return Decimal("0.00")
    s = re.sub(r"[¥￥,，\s元圆]", "", s)
    try:
        return Decimal(s).quantize(CENT, ROUND_HALF_UP)
    except InvalidOperation:
        return None


def fmt(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


def _four(n: int) -> str:
    """0 < n < 10000 的四位段读法（含段内的零）。"""
    out, zero = "", False
    for i in range(3, -1, -1):
        d = n // (10 ** i) % 10
        if d == 0:
            zero = bool(out)
        else:
            if zero:
                out += "零"
                zero = False
            out += _DIGITS[d] + _UNITS[i]
    return out


def to_chinese_upper(value) -> str:
    """金额转中文大写，写法与数电票“价税合计（大写）”一致，如 113.00 -> 壹佰壹拾叁圆整。"""
    amount = to_decimal(value)
    if amount is None:
        raise ValueError(f"不是金额: {value!r}")
    neg = amount < 0
    amount = abs(amount)
    cents = int((amount * 100).to_integral_value(ROUND_HALF_UP))
    integer, jiao, fen = cents // 100, cents // 10 % 10, cents % 10
    parts: list[str] = []
    if integer:
        sections = []
        while integer:
            sections.append(integer % 10000)
            integer //= 10000
        out, need_zero = "", False
        for idx in range(len(sections) - 1, -1, -1):
            sec = sections[idx]
            if sec == 0:
                need_zero = bool(out)
                continue
            if out and (need_zero or sec < 1000):
                out += "零"
            out += _four(sec) + _SECTIONS[idx]
            need_zero = False
        parts.append(out + "圆")
    if jiao == 0 and fen == 0:
        text = ("".join(parts) or "零圆") + "整"
    else:
        if jiao:
            parts.append(_DIGITS[jiao] + "角")
        elif parts:
            parts.append("零")
        if fen:
            parts.append(_DIGITS[fen] + "分")
        text = "".join(parts)
    return ("负" if neg else "") + text


def normalize_chinese_upper(s: str | None) -> str | None:
    """比较大写金额时忽略 ⊗、空格和 元/圆 写法差异。"""
    if not s:
        return None
    s = re.sub(r"[⊗ⓧ\s（）()]", "", s).replace("元", "圆")
    s = s.replace("角整", "角").replace("圆零", "圆")
    return s
