"""跨格式合并与去重：同一张票的 XML/OFD/PDF 合为一条，以 XML 为准；不一致时报出。"""
from __future__ import annotations

from .model import COMPARE_FIELDS, FIELD_LABELS, FIELDS, FORMAT_PRIORITY, Doc, Record
from .money import normalize_chinese_upper, to_chinese_upper


def _prio(d: Doc):
    return (FORMAT_PRIORITY.get(d.fmt, 9), d.name)


def merge_docs(docs: list[Doc]) -> list[Record]:
    groups: dict[str, list[Doc]] = {}
    order: list[str] = []
    records: list[Record] = []
    for d in docs:
        k = d.key
        if k is None:
            continue
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(d)

    for k in order:
        group = sorted(groups[k], key=_prio)
        sources, dups, seen = [], [], {}
        for d in group:
            if d.fmt in seen:
                dups.append(d)
            else:
                seen[d.fmt] = d
                sources.append(d)
        primary = sources[0]
        fields = {f: primary.fields[f] for f in FIELDS if f in primary.fields}
        for d in sources[1:]:  # 主文件缺的字段由其它格式补
            for f in FIELDS:
                if f not in fields and f in d.fields:
                    fields[f] = d.fields[f]
        rec = Record(key=k, fields=fields, primary=primary, sources=sources, duplicates=dups)
        for f in COMPARE_FIELDS:
            vals = {d.fmt: d.fields[f] for d in sources if f in d.fields}
            if len(set(vals.values())) > 1:
                rec.mismatches.append({"field": f, "label": FIELD_LABELS[f], "values": vals})
        for d in dups:
            same = "内容完全相同" if d.sha256 == seen[d.fmt].sha256 else "同号码的另一份文件"
            rec.warnings.append(f"重复文件：{d.name}（{same}，已跳过）")
        for d in sources:
            rec.warnings += [f"{d.name}：{w}" for w in d.warnings]
        if rec.mismatches:
            names = "、".join(m["label"] for m in rec.mismatches)
            base = "XML" if primary.fmt == "xml" else primary.fmt.upper()
            rec.warnings.append(f"不同格式的内容不一致（{names}），已以 {base} 为准，请核对")
        _consistency(rec)
        records.append(rec)

    # 没有号码的文件：单独成条，标“需人工”，并提示疑似重复
    for d in docs:
        if d.key is not None:
            continue
        rec = Record(key=f"unrecognized:{d.name}", fields=dict(d.fields), primary=d, sources=[d],
                     recognized=False)
        rec.warnings.append(d.error or "；".join(d.warnings) or "无法识别")
        f = d.fields
        if f.get("total") and f.get("date"):
            for r in records:
                if r.recognized and r.fields.get("total") == f["total"] and r.fields.get("date") == f["date"]:
                    rec.warnings.append(f"疑似与 {r.key} 重复（同日同额，无号码，未合并）")
        records.append(rec)
    return records


def _consistency(rec: Record) -> None:
    from decimal import Decimal
    f = rec.fields
    if f.get("amount") and f.get("tax") and f.get("total"):
        if Decimal(f["amount"]) + Decimal(f["tax"]) != Decimal(f["total"]):
            rec.warnings.append(f"金额 {f['amount']} + 税额 {f['tax']} ≠ 价税合计 {f['total']}")
    if f.get("total") and f.get("total_cn"):
        if normalize_chinese_upper(f["total_cn"]) != normalize_chinese_upper(to_chinese_upper(f["total"])):
            rec.warnings.append(f"大写金额“{f['total_cn']}”与小写 {f['total']} 不符")
    missing = [k for k in ("number", "date", "seller_name", "buyer_name", "total") if not f.get(k)]
    if missing:
        rec.warnings.append("缺少字段：" + "、".join(FIELD_LABELS[m] for m in missing) + "，需人工核对")
