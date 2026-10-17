from decimal import Decimal

import pytest

from fapiao_kit.money import normalize_chinese_upper, to_chinese_upper, to_decimal


@pytest.mark.parametrize("value,expected", [
    ("0", "零圆整"), ("0.05", "伍分"), ("0.50", "伍角"), ("1", "壹圆整"), ("10", "壹拾圆整"),
    ("113.00", "壹佰壹拾叁圆整"), ("1005.50", "壹仟零伍圆伍角"), ("1010", "壹仟零壹拾圆整"),
    ("100000.01", "壹拾万圆零壹分"), ("100100", "壹拾万零壹佰圆整"), ("10001", "壹万零壹圆整"),
    ("108000000", "壹亿零捌佰万圆整"), ("123456789.12", "壹亿贰仟叁佰肆拾伍万陆仟柒佰捌拾玖圆壹角贰分"),
    ("-58.30", "负伍拾捌圆叁角"),
])
def test_chinese_upper(value, expected):
    assert to_chinese_upper(value) == expected


@pytest.mark.parametrize("raw,expected", [
    ("¥1,234.5", Decimal("1234.50")), ("￥ 88", Decimal("88.00")), ("***", Decimal("0.00")),
    ("免税", Decimal("0.00")), ("abc", None), ("", None), (None, None), ("-3.333", Decimal("-3.33")),
])
def test_to_decimal(raw, expected):
    assert to_decimal(raw) == expected


def test_upper_normalize_tolerates_variants():
    assert normalize_chinese_upper("⊗壹拾圆零伍角整") == normalize_chinese_upper("壹拾元伍角")
