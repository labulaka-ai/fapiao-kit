"""按版面（文字 + 坐标）抽取发票字段。PDF 与无标签 OFD 共用。

token: (x, y, x_end, text, size)，坐标单位任意，但 y 必须自上而下递增。
"""
from __future__ import annotations

import re

AMT = r"-?[\d,]+\.\d{2}"
TAX_LABEL = r"(?:统一社会信用代码\s*/\s*纳税人识别号|纳税人识别号|统一社会信用代码)"
NAME_RE = re.compile(r"名\s*称\s*[:：]\s*(.*)")
TAXID_RE = re.compile(TAX_LABEL + r"\s*[:：]?\s*([0-9A-Za-z]{15,20})")


def build_lines(tokens, page_height):
    """按 y 聚成行，行内按 x 排序，再把间距很小的 token 拼成段。返回 [(y, [(x, text)])]。"""
    tol = max(page_height * 0.008, 0.5)
    rows: list[list] = []
    for t in sorted(tokens, key=lambda t: (t[1], t[0])):
        if rows and abs(rows[-1][0][1] - t[1]) <= tol:
            rows[-1].append(t)
        else:
            rows.append([t])
    lines = []
    for row in rows:
        row.sort(key=lambda t: t[0])
        segs: list[list] = []
        for t in row:
            if segs:
                prev = segs[-1]
                gap = t[0] - prev[2]
                if gap <= max(t[4], prev[3]) * 1.2:
                    prev[1] += t[3]
                    prev[2] = max(prev[2], t[2])
                    prev[3] = max(prev[3], t[4])
                    continue
            segs.append([t[0], t[3], t[2], t[4]])
        lines.append((row[0][1], [(s[0], s[1].strip()) for s in segs if s[1].strip()]))
    return [l for l in lines if l[1]]


def _assign_parties(hits, page_width):
    """hits: [(x, y, value)]。左右分栏时左=购买方；上下排列（旧版）时上=购买方。"""
    if not hits:
        return None, None
    if len(hits) == 1:
        x, y, v = hits[0]
        return (v, None) if x < page_width / 2 else (None, v)
    hits = sorted(hits, key=lambda h: (h[1], h[0]))[:4]
    xs = [h[0] for h in hits]
    if max(xs) - min(xs) > page_width * 0.25:
        left = min(hits, key=lambda h: h[0])
        right = max(hits, key=lambda h: h[0])
        return left[2], right[2]
    return hits[0][2], hits[1][2]


def extract_fields(tokens, page_width, page_height):
    """返回 (fields, items, text)。字段值未规范化。"""
    lines = build_lines(tokens, page_height)
    text = "\n".join(" ".join(s for _, s in segs) for _, segs in lines)
    f: dict = {}
    m = re.search(r"发票号码\s*[:：]?\s*(\d{8,20})", text)
    if m:
        f["number"] = m[1]
    m = re.search(r"发票代码\s*[:：]?\s*(\d{10,12})", text)
    if m:
        f["code"] = m[1]
    m = re.search(r"开票日期\s*[:：]?\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}-\d{1,2}-\d{1,2})", text)
    if m:
        f["date"] = m[1]

    names, taxids = [], []
    for y, segs in lines:
        for x, s in segs:
            nm = NAME_RE.search(s)
            if nm and nm[1].strip():
                names.append((x, y, nm[1].strip()))
            tm = TAXID_RE.search(s)
            if tm:
                taxids.append((x, y, tm[1]))
    f["buyer_name"], f["seller_name"] = _assign_parties(names, page_width)
    f["buyer_tax_id"], f["seller_tax_id"] = _assign_parties(taxids, page_width)

    m = re.search(r"[（(]\s*小\s*写\s*[）)]\s*[¥￥]?\s*(" + AMT + ")", text)
    if m:
        f["total"] = m[1]
    m = re.search(r"价税合计\s*[（(]\s*大\s*写\s*[）)]\s*[⊗ⓧ]?\s*([零壹贰叁肆伍陆柒捌玖拾佰仟万亿圆元角分整负]+)", text)
    if m:
        f["total_cn"] = m[1]
    for _, segs in lines:
        line = " ".join(s for _, s in segs)
        if re.match(r"\s*合\s*计", line) and "价税" not in line:
            nums = re.findall(r"[¥￥]\s*(" + AMT + ")", line)
            if nums:
                f["amount"] = nums[0]
                if len(nums) > 1:
                    f["tax"] = nums[1]
                elif "*" in line:
                    f["tax"] = "0.00"
            break
    items = []
    for mm in re.finditer(r"\*([^*\s]+)\*([^\s¥￥]*)", text):
        items.append({"name": f"*{mm[1]}*{mm[2]}"})
    if items:
        f["category"] = re.match(r"\*([^*]+)\*", items[0]["name"])[1]
    if "专用发票" in text:
        f["invoice_type"] = "增值税专用发票"
    elif "普通发票" in text:
        f["invoice_type"] = "普通发票"
    return {k: v for k, v in f.items() if v}, items, text
