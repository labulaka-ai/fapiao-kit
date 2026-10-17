"""导出 Excel 汇总表：明细、合计、大写金额、按类别小计、需处理清单。"""
from __future__ import annotations

from decimal import Decimal

from .model import Record
from .money import to_chinese_upper
from .xlsx import write_xlsx

HEADERS = ["序号", "开票日期", "发票号码", "发票代码", "票种", "类别", "销售方", "销售方税号",
           "购买方", "购买方税号", "金额", "税额", "价税合计", "文件格式", "问题"]
WIDTHS = [6, 12, 24, 14, 16, 12, 28, 22, 28, 22, 12, 12, 12, 12, 50]


def _dec(v):
    return Decimal(v) if v else None


def totals(records: list[Record]) -> dict:
    ok = [r for r in records if r.recognized]
    s = {k: sum((Decimal(r.fields[k]) for r in ok if r.fields.get(k)), Decimal("0.00")) for k in ("amount", "tax", "total")}
    return {"count": len(ok), "amount": f"{s['amount']:.2f}", "tax": f"{s['tax']:.2f}",
            "total": f"{s['total']:.2f}", "total_cn": to_chinese_upper(s["total"]),
            "unrecognized": len(records) - len(ok)}


def _problems(r: Record) -> str:
    msgs = [i["message"] for i in r.issues] if r.issues else []
    if not r.issues:
        msgs = list(r.warnings)
    return "；".join(dict.fromkeys(msgs))


def build_xlsx(records: list[Record]) -> bytes:
    ok = sorted([r for r in records if r.recognized], key=lambda r: (r.fields.get("date") or "", r.key))
    rows = [[(h, 1) for h in HEADERS]]
    for i, r in enumerate(ok, start=1):
        f = r.fields
        rows.append([(i, 0), (f.get("date"), 3), (f.get("number"), 3), (f.get("code"), 3),
                     (f.get("invoice_type"), 0), (f.get("category"), 0),
                     (f.get("seller_name"), 0), (f.get("seller_tax_id"), 3),
                     (f.get("buyer_name"), 0), (f.get("buyer_tax_id"), 3),
                     (_dec(f.get("amount")), 2), (_dec(f.get("tax")), 2), (_dec(f.get("total")), 2),
                     ("+".join(x.upper() for x in r.formats), 0), (_problems(r) or None, 0)])
    t = totals(records)
    blank = [(None, 0)] * 10
    rows.append([("合计", 1)] + [(None, 0)] * 9 + [(Decimal(t["amount"]), 4), (Decimal(t["tax"]), 4), (Decimal(t["total"]), 4)])
    rows.append([("合计（大写）", 1), (None, 0), (t["total_cn"], 5)])
    rows.append([("张数", 1), (None, 0), (t["count"], 1)])
    if t["unrecognized"]:
        rows.append([("未识别", 1), (None, 0), (f"{t['unrecognized']} 个文件未能识别，未计入合计，见“需处理”表", 0)])
    del blank

    cats: dict[str, list] = {}
    for r in ok:
        cats.setdefault(r.fields.get("category") or "（未识别类别）", []).append(r)
    cat_rows = [[(h, 1) for h in ["类别", "张数", "金额", "税额", "价税合计"]]]
    for c, rs in sorted(cats.items()):
        s = {k: sum((Decimal(x.fields[k]) for x in rs if x.fields.get(k)), Decimal("0.00")) for k in ("amount", "tax", "total")}
        cat_rows.append([(c, 0), (len(rs), 0), (s["amount"], 2), (s["tax"], 2), (s["total"], 2)])
    cat_rows.append([("合计", 1), (t["count"], 1), (Decimal(t["amount"]), 4), (Decimal(t["tax"]), 4), (Decimal(t["total"]), 4)])

    todo = [[(h, 1) for h in ["发票号码 / 文件", "级别", "问题"]]]
    for r in records:
        for i in r.issues:
            todo.append([(r.fields.get("number") or r.primary.name, 3), ("错误" if i["level"] == "error" else "提示", 0), (i["message"], 0)])
        if not r.issues and not r.recognized:
            todo.append([(r.primary.name, 3), ("错误", 0), ("；".join(r.warnings), 0)])
    return write_xlsx([("汇总", rows, WIDTHS), ("按类别小计", cat_rows, [20, 8, 14, 14, 14]),
                       ("需处理", todo, [28, 8, 80])])
