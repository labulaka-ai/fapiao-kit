"""抬头、税号等规则检查。规则文件为 TOML（标准库 tomllib，无需额外依赖）。

示例：
    buyer_name = "示例大学"
    buyer_tax_id = "99TEST000000000001"
    date_from = "2026-01-01"       # 可选
    date_to = "2026-12-31"         # 可选
    [category_limits]              # 可选：单张价税合计上限
    "餐饮服务" = 500
"""
from __future__ import annotations

from decimal import Decimal

from .model import Record, norm_name, norm_tax_id


def load_rules(path: str) -> dict:
    import tomllib
    with open(path, "rb") as f:
        return tomllib.load(f)


def check_records(records: list[Record], rules: dict | None = None) -> list[Record]:
    """在每条记录的 issues 里写入 {level: error|warning, rule, message}。返回原列表。"""
    rules = rules or {}
    want_name = norm_name(rules.get("buyer_name") or None)
    want_tax = norm_tax_id(rules.get("buyer_tax_id") or None)
    limits = {k: Decimal(str(v)) for k, v in (rules.get("category_limits") or {}).items()}
    for r in records:
        issues = []
        f = r.fields

        def add(level, rule, msg):
            issues.append({"level": level, "rule": rule, "message": msg})

        if not r.recognized:
            add("error", "unrecognized", "无法自动识别，需人工录入：" + "；".join(r.warnings))
            r.issues = issues
            continue
        if want_name and f.get("buyer_name") and f["buyer_name"] != want_name:
            add("error", "buyer_name", f"购买方名称“{f['buyer_name']}”与单位抬头“{want_name}”不一致")
        if want_tax and f.get("buyer_tax_id") and f["buyer_tax_id"] != want_tax:
            add("error", "buyer_tax_id", f"购买方税号 {f['buyer_tax_id']} 与单位税号 {want_tax} 不一致")
        if want_name and not f.get("buyer_name"):
            add("warning", "buyer_name", "没有识别出购买方名称，请人工核对抬头")
        if want_tax and not f.get("buyer_tax_id"):
            add("warning", "buyer_tax_id", "没有识别出购买方税号，请人工核对")
        if r.mismatches:
            add("error", "mismatch", "不同格式内容不一致：" + "；".join(
                f"{m['label']} " + " / ".join(f"{k.upper()}={v}" for k, v in m["values"].items()) for m in r.mismatches))
        if r.duplicates:
            add("warning", "duplicate", f"有 {len(r.duplicates)} 个重复文件，已只计一次")
        if f.get("date"):
            if rules.get("date_from") and f["date"] < str(rules["date_from"]):
                add("error", "date_range", f"开票日期 {f['date']} 早于 {rules['date_from']}")
            if rules.get("date_to") and f["date"] > str(rules["date_to"]):
                add("error", "date_range", f"开票日期 {f['date']} 晚于 {rules['date_to']}")
        cat = f.get("category")
        if cat in limits and f.get("total") and Decimal(f["total"]) > limits[cat]:
            add("error", "category_limit", f"{cat} 单张 {f['total']} 元，超过上限 {limits[cat]} 元")
        if f.get("total") and Decimal(f["total"]) < 0:
            add("warning", "negative", "负数发票（红冲），请确认是否应报销")
        for w in r.warnings:
            if w.startswith(("金额 ", "大写金额", "缺少字段")):
                add("warning", "consistency", w)
        r.issues = issues
    return records


def has_errors(records: list[Record]) -> bool:
    return any(i["level"] == "error" for r in records for i in r.issues)
