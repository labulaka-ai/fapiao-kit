"""规则检查：每条规则一个“检出”用例 + 一个“不误报”用例。"""
import pytest

from fapiao_kit.merge import merge_docs
from fapiao_kit.model import Doc
from fapiao_kit.rules import check_records, has_errors, load_rules

GOOD = {"number": "99260000000000000100", "date": "2026-05-01", "seller_name": "示例销售有限公司",
        "seller_tax_id": "99TEST0000000000Z9", "buyer_name": "示例大学", "buyer_tax_id": "99TEST000000000001",
        "amount": "100.00", "tax": "6.00", "total": "106.00", "total_cn": "壹佰零陆圆整", "category": "餐饮服务"}
RULES = {"buyer_name": "示例大学", "buyer_tax_id": "99TEST000000000001", "date_from": "2026-01-01",
         "date_to": "2026-12-31", "category_limits": {"餐饮服务": 500}}


def run(fields, rules=RULES):
    rec = merge_docs([Doc("x.xml", "xml", "h", fields=dict(fields))])[0]
    check_records([rec], rules)
    return [i["rule"] for i in rec.issues], rec


def test_clean_invoice_no_issues():
    rules, rec = run(GOOD)
    assert rules == [] and not has_errors([rec])


@pytest.mark.parametrize("change,rule", [
    ({"buyer_name": "示例大字"}, "buyer_name"),
    ({"buyer_tax_id": "99TEST000000000009"}, "buyer_tax_id"),
    ({"date": "2025-12-31"}, "date_range"),
    ({"date": "2027-01-01"}, "date_range"),
    ({"amount": "600.00", "tax": "36.00", "total": "636.00", "total_cn": "陆佰叁拾陆圆整"}, "category_limit"),
    ({"total": "107.00", "total_cn": "壹佰零柒圆整"}, "consistency"),
    ({"total_cn": "壹佰零柒圆整"}, "consistency"),
])
def test_rule_detects(change, rule):
    rules, _ = run({**GOOD, **change})
    assert rule in rules


def test_bracket_and_space_normalization_no_false_positive():
    rules, _ = run({**GOOD, "buyer_name": "示例大学"}, {"buyer_name": " 示例大学 "})
    assert rules == []
    rules, _ = run({**GOOD, "buyer_name": "示例（北京）大学"}, {"buyer_name": "示例(北京)大学"})
    assert rules == []


def test_lowercase_tax_id_in_rules_ok():
    rules, _ = run(GOOD, {"buyer_tax_id": "99test000000000001"})
    assert rules == []


def test_no_rules_no_title_check():
    rules, _ = run({**GOOD, "buyer_name": "别的单位"}, {})
    assert rules == []


def test_mismatch_and_duplicate_rules():
    a = Doc("a.xml", "xml", "1", fields=dict(GOOD))
    b = Doc("a.pdf", "pdf", "2", fields={**GOOD, "total": "999.00"})
    c = Doc("a(1).pdf", "pdf", "3", fields={**GOOD, "total": "999.00"})
    rec = merge_docs([c, b, a])[0]
    check_records([rec], RULES)
    rules = [i["rule"] for i in rec.issues]
    assert "mismatch" in rules and "duplicate" in rules
    assert rec.fields["total"] == "106.00"


def test_negative_invoice_warning():
    rules, _ = run({**GOOD, "amount": "-100.00", "tax": "-6.00", "total": "-106.00", "total_cn": "负壹佰零陆圆整"})
    assert "negative" in rules


def test_sample_set_rules(records, sample_set):
    _, truth = sample_set
    for key, exp in truth["records"].items():
        got = sorted({i["rule"] for i in records[key].issues})
        assert got == sorted(exp["issues"]), key
    for r in records.values():
        if not r.recognized:
            assert [i["rule"] for i in r.issues] == ["unrecognized"]


def test_load_rules_toml(tmp_path):
    p = tmp_path / "r.toml"
    p.write_text('buyer_name = "示例大学"\nbuyer_tax_id = "99TEST000000000001"\n[category_limits]\n"餐饮服务" = 500\n',
                 encoding="utf-8")
    r = load_rules(str(p))
    assert r["buyer_name"] == "示例大学" and r["category_limits"]["餐饮服务"] == 500


def test_example_rule_file_loads():
    import os
    r = load_rules(os.path.join(os.path.dirname(__file__), "..", "rules", "example.toml"))
    assert r["buyer_name"] and r["buyer_tax_id"]
