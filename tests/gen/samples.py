"""合成测试样本生成器（全部自写，不使用任何真实发票或官方样例文件）。

硬约束（防止被误当作真票）：
- 每个文件都带“测试样例 非真实发票”字样（PDF/OFD 为水印文字，XML 为注释和备注）；
- 公司名称全部虚构（“示例”“虚构”“样例”开头），税号以 99TEST 开头，明显无效；
- 发票号码使用 99 开头的号段，旧版发票代码为 999999999999；
- 不画任何印章、监制章或税务机关标志。
"""
from __future__ import annotations

import io
import os
import random
import zipfile
from decimal import Decimal
from xml.sax.saxutils import escape

from fapiao_kit.money import to_chinese_upper

WATERMARK = "测试样例 非真实发票"
BUYER = ("示例大学", "99TEST000000000001")


def make_spec(number, date, seller, seller_id, items, buyer=BUYER[0], buyer_id=BUYER[1],
              kind="增值税专用发票", code=None):
    """items: [(名称, 金额, 税率%)]，税额按四舍五入到分。"""
    rows = []
    for name, amt, rate in items:
        amt = Decimal(str(amt)).quantize(Decimal("0.01"))
        tax = (amt * Decimal(rate) / 100).quantize(Decimal("0.01"))
        rows.append({"name": name, "amount": f"{amt:.2f}", "rate": f"{rate}%", "tax": f"{tax:.2f}"})
    amount = sum(Decimal(r["amount"]) for r in rows)
    tax = sum(Decimal(r["tax"]) for r in rows)
    total = amount + tax
    return {"number": number, "code": code, "date": date, "invoice_type": kind,
            "seller_name": seller, "seller_tax_id": seller_id, "buyer_name": buyer, "buyer_tax_id": buyer_id,
            "items": rows, "amount": f"{amount:.2f}", "tax": f"{tax:.2f}", "total": f"{total:.2f}",
            "total_cn": to_chinese_upper(total), "category": rows[0]["name"].split("*")[1]}


def truth(spec) -> dict:
    keys = ["number", "code", "date", "invoice_type", "seller_name", "seller_tax_id", "buyer_name",
            "buyer_tax_id", "amount", "tax", "total", "category"]
    return {k: spec[k] for k in keys if spec.get(k)}


def cn_date(iso):
    y, m, d = iso.split("-")
    return f"{y}年{m}月{d}日"


# ------------------------------------------------------------------ XML
def make_xml(spec) -> bytes:
    items = "".join(
        f"<IssuItemInformation><ItemName>{escape(i['name'])}</ItemName><SpecMod/><MeaUnits>项</MeaUnits>"
        f"<Quantity>1</Quantity><UnPrice>{i['amount']}</UnPrice><Amount>{i['amount']}</Amount>"
        f"<TaxRate>{i['rate']}</TaxRate><ComTaxAm>{i['tax']}</ComTaxAm></IssuItemInformation>"
        for i in spec["items"])
    s = spec
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- {WATERMARK}：fapiao-kit 测试用合成数据，不具备任何效力 -->
<EInvoice>
  <Header><EIid>{s['number']}</EIid><Version>test</Version>
    <InherentLabel><EInvoiceType><LabelCode>00</LabelCode><LabelName>{s['invoice_type']}</LabelName></EInvoiceType></InherentLabel>
  </Header>
  <EInvoiceData>
    <SellerInformation><SellerIdNum>{s['seller_tax_id']}</SellerIdNum><SellerName>{escape(s['seller_name'])}</SellerName></SellerInformation>
    <BuyerInformation><BuyerIdNum>{s['buyer_tax_id']}</BuyerIdNum><BuyerName>{escape(s['buyer_name'])}</BuyerName></BuyerInformation>
    <BasicInformation><TotalAmWithoutTax>{s['amount']}</TotalAmWithoutTax><TotalTaxAm>{s['tax']}</TotalTaxAm>
      <TotalTax-includedAmount>{s['total']}</TotalTax-includedAmount>
      <TotalTax-includedAmountInChinese>{s['total_cn']}</TotalTax-includedAmountInChinese>
      <Drawer>测试</Drawer><RequestTime>{s['date']} 10:00:00</RequestTime></BasicInformation>
    {items}
    <AdditionalInformation><Remark>{WATERMARK}</Remark></AdditionalInformation>
  </EInvoiceData>
  <TaxSupervisionInfo><InvoiceNumber>{s['number']}</InvoiceNumber><IssueTime>{s['date']}</IssueTime>
    <TaxBureauName>{WATERMARK}</TaxBureauName></TaxSupervisionInfo>
</EInvoice>
"""
    return xml.encode("utf-8")


# ------------------------------------------------------------------ 共用版面
def layout_lines(spec, old=False, override=None):
    """返回 [(x_mm, y_mm, text, size_mm, tag)]，y 自上而下，页面 210x140mm。tag 用于 OFD 自定义标签。"""
    s = dict(spec)
    s.update(override or {})
    L = []
    add = lambda x, y, t, size=3.0, tag=None: L.append((x, y, t, size, tag))
    if old:
        add(60, 12, "增值税电子普通发票", 5.0)
        add(140, 20, "发票代码：", 2.8)
        add(155, 20, s["code"], 2.8, "InvoiceCode")
        add(140, 25, "发票号码：", 2.8)
        add(155, 25, s["number"], 2.8, "InvoiceNo")
        add(140, 30, "开票日期：", 2.8)
        add(155, 30, cn_date(s["date"]), 2.8, "IssueDate")
        by_name, by_tax, sx = (12, 40), (12, 45), None
        add(5, 42, "购买方", 3.0)
        add(12, 40, "名称：", 2.8)
        add(21, 40, s["buyer_name"], 2.8, "BuyerName")
        add(12, 45, "纳税人识别号：", 2.8)
        add(33, 45, s["buyer_tax_id"], 2.8, "BuyerTaxID")
        del by_name, by_tax, sx
    else:
        kind = "电子发票（增值税专用发票）" if "专用" in s["invoice_type"] else "电子发票（普通发票）"
        add(60, 12, kind, 5.0)
        add(140, 20, "发票号码：", 2.8)
        add(155, 20, s["number"], 2.8, "InvoiceNo")
        add(140, 25, "开票日期：", 2.8)
        add(155, 25, cn_date(s["date"]), 2.8, "IssueDate")
        for side, x0, nm, tid, tn, tt in ((0, 12, s["buyer_name"], s["buyer_tax_id"], "BuyerName", "BuyerTaxID"),
                                          (1, 112, s["seller_name"], s["seller_tax_id"], "SellerName", "SellerTaxID")):
            add(x0 - 7, 40, "购买方信息" if side == 0 else "销售方信息", 2.5)
            add(x0, 38, "名称：", 2.8)
            add(x0 + 9, 38, nm, 2.8, tn)
            add(x0, 45, "统一社会信用代码/纳税人识别号：", 2.2)
            add(x0 + 36, 45, tid, 2.2, tt)
    y = 58
    add(12, y, "项目名称", 2.5)
    add(110, y, "金额", 2.5)
    add(140, y, "税率/征收率", 2.5)
    add(175, y, "税额", 2.5)
    for it in s["items"]:
        y += 6
        add(12, y, it["name"], 2.5)
        add(110, y, it["amount"], 2.5)
        add(140, y, it["rate"], 2.5)
        add(175, y, it["tax"], 2.5)
    add(12, 100, "合 计", 2.8)
    add(108, 100, "¥" + s["amount"], 2.8, "TaxExclusiveTotalAmount")
    add(173, 100, "¥" + s["tax"], 2.8, "TaxTotalAmount")
    add(12, 108, "价税合计（大写）", 2.8)
    add(60, 108, "⊗" + s["total_cn"], 2.8)
    add(140, 108, "（小写）", 2.8)
    add(153, 108, "¥" + s["total"], 2.8, "TaxInclusiveTotalAmount")
    if old:
        add(5, 120, "销售方", 3.0)
        add(12, 118, "名称：", 2.8)
        add(21, 118, s["seller_name"], 2.8, "SellerName")
        add(12, 123, "纳税人识别号：", 2.8)
        add(33, 123, s["seller_tax_id"], 2.8, "SellerTaxID")
    add(12, 132, "开票人：测试", 2.5)
    return L


# ------------------------------------------------------------------ PDF
def make_pdf(spec, old=False, override=None) -> bytes:
    from reportlab.lib.colors import Color
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas
    if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    mm = 72 / 25.4
    W, H = 210 * mm, 140 * mm
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(WATERMARK)
    for x, y, t, size, _ in layout_lines(spec, old, override):
        c.setFont("STSong-Light", size * mm)
        c.drawString(x * mm, H - y * mm, t)
    c.saveState()  # 水印：不画印章，只有大字“测试样例 非真实发票”
    c.setFillColor(Color(0.6, 0.6, 0.6, alpha=0.35))
    c.setFont("STSong-Light", 16 * mm)
    c.translate(40 * mm, 18 * mm)
    c.rotate(12)
    c.drawString(0, 0, WATERMARK)
    c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()


def make_image_pdf() -> bytes:
    """没有文字层的 PDF（模拟扫描件）。"""
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(595, 397))
    for i in range(10):
        c.rect(30 + i * 50, 100, 40, 200, fill=i % 2)
    c.showPage()
    c.save()
    return buf.getvalue()


# ------------------------------------------------------------------ OFD
NS = 'xmlns:ofd="http://www.ofdspec.org/2016"'


def make_ofd(spec, variant="tags", override=None, old=False) -> bytes:
    """variant: tags（自定义标签指向文字对象）/ deltax（无标签，标签与值同一 TextCode，逐字 DeltaX）/
    multiseg（OFD.xml CustomData 给号码金额，名称拆成多段 TextCode）。"""
    lines = layout_lines(spec, old, override)
    objs, tag_refs = [], {}
    oid = 100
    merged = []
    if variant == "deltax":  # 把“标签：”和紧随其后的值合并成一个 TextCode
        i = 0
        while i < len(lines):
            x, y, t, size, tag = lines[i]
            if t.endswith("：") and i + 1 < len(lines) and lines[i + 1][1] == y:
                merged.append((x, y, t + lines[i + 1][2], size, lines[i + 1][4]))
                i += 2
            else:
                merged.append(lines[i])
                i += 1
        lines = merged
    for x, y, t, size, tag in lines:
        oid += 1
        esc = escape(t)
        if variant == "deltax" and len(t) > 1:
            code = f'<ofd:TextCode X="0" Y="{size:.2f}" DeltaX="g {len(t) - 1} {size:.2f}">{esc}</ofd:TextCode>'
        elif variant == "multiseg" and tag in ("BuyerName", "SellerName") and len(t) > 4:
            half = len(t) // 2
            code = (f'<ofd:TextCode X="0" Y="{size:.2f}">{escape(t[:half])}</ofd:TextCode>'
                    f'<ofd:TextCode X="{half * size:.2f}" Y="{size:.2f}">{escape(t[half:])}</ofd:TextCode>')
        else:
            code = f'<ofd:TextCode X="0" Y="{size:.2f}">{esc}</ofd:TextCode>'
        w = len(t) * size
        objs.append(f'<ofd:TextObject ID="{oid}" Boundary="{x:.2f} {y - size:.2f} {w:.2f} {size * 1.4:.2f}" '
                    f'Font="1" Size="{size:.2f}">{code}</ofd:TextObject>')
        if tag:
            tag_refs[tag] = oid
    oid += 1
    objs.append(f'<ofd:TextObject ID="{oid}" Boundary="40 10 160 30" Font="1" Size="16" Alpha="80">'
                f'<ofd:TextCode X="0" Y="16">{WATERMARK}</ofd:TextCode></ofd:TextObject>')
    s = dict(spec)
    s.update(override or {})
    custom = ""
    if variant == "multiseg":
        cd = {"发票号码": s["number"], "开票日期": s["date"], "合计金额": s["amount"], "合计税额": s["tax"],
              "购买方纳税人识别号": s["buyer_tax_id"], "销售方纳税人识别号": s["seller_tax_id"]}
        if s.get("code"):
            cd["发票代码"] = s["code"]
        custom = "<ofd:CustomDatas>" + "".join(
            f'<ofd:CustomData Name="{k}">{escape(v)}</ofd:CustomData>' for k, v in cd.items()) + "</ofd:CustomDatas>"
    ofd_xml = (f'<?xml version="1.0" encoding="UTF-8"?><ofd:OFD {NS} Version="1.0" DocType="OFD"><ofd:DocBody>'
               f'<ofd:DocInfo><ofd:DocID>test-{s["number"]}</ofd:DocID><ofd:Title>{WATERMARK}</ofd:Title>{custom}</ofd:DocInfo>'
               '<ofd:DocRoot>Doc_0/Document.xml</ofd:DocRoot></ofd:DocBody></ofd:OFD>')
    tags_decl = "<ofd:CustomTags>Tags/CustomTags.xml</ofd:CustomTags>" if variant == "tags" else ""
    document = (f'<?xml version="1.0" encoding="UTF-8"?><ofd:Document {NS}><ofd:CommonData>'
                f'<ofd:MaxUnitID>{oid}</ofd:MaxUnitID><ofd:PageArea><ofd:PhysicalBox>0 0 210 140</ofd:PhysicalBox></ofd:PageArea>'
                '</ofd:CommonData><ofd:Pages><ofd:Page ID="1" BaseLoc="Pages/Page_0/Content.xml"/></ofd:Pages>'
                f'{tags_decl}</ofd:Document>')
    content = (f'<?xml version="1.0" encoding="UTF-8"?><ofd:Page {NS}><ofd:Content><ofd:Layer ID="2">'
               + "".join(objs) + '</ofd:Layer></ofd:Content></ofd:Page>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("OFD.xml", ofd_xml)
        z.writestr("Doc_0/Document.xml", document)
        z.writestr("Doc_0/Pages/Page_0/Content.xml", content)
        if variant == "tags":
            z.writestr("Doc_0/Tags/CustomTags.xml",
                       f'<?xml version="1.0" encoding="UTF-8"?><ofd:CustomTags {NS}><ofd:CustomTag NameSpace="urn:fapiao-kit:test">'
                       '<ofd:FileLoc>CustomTag.xml</ofd:FileLoc></ofd:CustomTag></ofd:CustomTags>')
            body = "".join(f'<t:{k}><ofd:ObjectRef PageRef="1">{v}</ofd:ObjectRef></t:{k}>' for k, v in tag_refs.items())
            z.writestr("Doc_0/Tags/CustomTag.xml",
                       f'<?xml version="1.0" encoding="UTF-8"?><t:Invoice xmlns:t="urn:fapiao-kit:test" {NS}>{body}</t:Invoice>')
    return buf.getvalue()


# ------------------------------------------------------------------ 样本集
SELLERS = [("虚构餐饮管理有限公司", "99TEST0000000000A1"), ("示例办公用品有限公司", "99TEST0000000000B2"),
           ("样例酒店管理有限公司", "99TEST0000000000C3"), ("虚构出行服务有限公司", "99TEST0000000000D4"),
           ("示例图书（北京）有限公司", "99TEST0000000000E5"), ("样例信息技术有限公司", "99TEST0000000000F6")]


def build_sample_set(out_dir: str) -> dict:
    """写出一批覆盖各种情况的样本，返回标准答案：
    {"records": {key: {"fields":..., "formats": [...], "duplicates": n, "mismatch": [...]}},
     "unrecognized": [文件名], "files": [文件名], "rules": {...}}"""
    os.makedirs(out_dir, exist_ok=True)
    rec, files = {}, []

    def w(name, data):
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(data)
        files.append(name)

    def expect(spec, formats, duplicates=0, mismatch=(), issues=()):
        key = f"{spec['code']}-{spec['number']}" if spec.get("code") else spec["number"]
        rec[key] = {"fields": truth(spec), "formats": formats, "duplicates": duplicates,
                    "mismatch": list(mismatch), "issues": list(issues)}

    # A 三件套：XML + OFD(标签) + PDF，专票，餐饮 → 合为 1 条
    a = make_spec("99260000000000000001", "2026-03-05", *SELLERS[0], [("*餐饮服务*餐费", "283.02", 6)])
    w("A_发票.xml", make_xml(a)); w("A_发票.ofd", make_ofd(a, "tags")); w("A_发票.pdf", make_pdf(a))
    expect(a, ["xml", "ofd", "pdf"])
    # B 只有 XML，普票，多行明细
    b = make_spec("99260000000000000002", "2026-03-08", *SELLERS[1],
                  [("*纸制品*打印纸", "120.00", 13), ("*文具*中性笔", "35.40", 13)], kind="普通发票")
    w("B.xml", make_xml(b)); expect(b, ["xml"])
    # C OFD 无标签 + DeltaX（版面兜底）
    c = make_spec("99260000000000000003", "2026-03-10", *SELLERS[2], [("*住宿服务*住宿费", "452.83", 6)])
    w("C 住宿.ofd", make_ofd(c, "deltax")); expect(c, ["ofd"])
    # D OFD CustomData + 多段 TextCode
    d = make_spec("99260000000000000004", "2026-03-12", *SELLERS[4], [("*图书*专业书籍", "88.00", 0)], kind="普通发票")
    w("D.ofd", make_ofd(d, "multiseg")); expect(d, ["ofd"])
    # E 只有 PDF，普票；G 是 E 改名后的重复副本
    e = make_spec("99260000000000000005", "2026-03-15", *SELLERS[3], [("*运输服务*客运服务费", "97.09", 3)], kind="普通发票")
    pdf_e = make_pdf(e)
    w("E 打车.pdf", pdf_e); w("E 打车(1).pdf", pdf_e)
    expect(e, ["pdf"], duplicates=1, issues=["duplicate"])
    # F 旧版增值税电子普通发票（代码+号码，上下排列）
    f = make_spec("99000001", "2019-05-06", *SELLERS[5], [("*信息技术服务*软件服务", "500.00", 6)],
                  kind="普通发票", code="999999999999")
    w("F_旧版.pdf", make_pdf(f, old=True)); expect(f, ["pdf"])
    # H 被改过的 PDF：XML 为准，标出价税合计不一致
    h = make_spec("99260000000000000006", "2026-03-18", *SELLERS[0], [("*餐饮服务*餐费", "188.68", 6)])
    w("H.xml", make_xml(h)); w("H.pdf", make_pdf(h, override={"total": "300.00", "total_cn": to_chinese_upper("300")}))
    expect(h, ["xml", "pdf"], mismatch=["total"], issues=["mismatch"])
    # I 抬头错一个字；J 税号错
    i = make_spec("99260000000000000007", "2026-03-20", *SELLERS[1], [("*文具*文件夹", "50.00", 13)],
                  buyer="示例大字", kind="普通发票")
    w("I.xml", make_xml(i)); expect(i, ["xml"], issues=["buyer_name"])
    j = make_spec("99260000000000000008", "2026-03-21", *SELLERS[1], [("*文具*订书机", "40.00", 13)],
                  buyer_id="99TEST000000000009", kind="普通发票")
    w("J.pdf", make_pdf(j)); expect(j, ["pdf"], issues=["buyer_tax_id"])
    # K 与 E 同日同额同销售方，但号码不同 → 不能合并
    k = make_spec("99260000000000000009", "2026-03-15", *SELLERS[3], [("*运输服务*客运服务费", "97.09", 3)], kind="普通发票")
    w("K.pdf", make_pdf(k)); expect(k, ["pdf"])
    # L 损坏文件；M 没有文字层的 PDF；乱码文件名的 OFD（内容为 A 的副本 → 重复）
    w("L_损坏.pdf", b"%PDF-1.7\n this is not a real pdf \x00\x01")
    w("L_损坏.ofd", b"PK\x03\x04 broken")
    w("M_扫描件.pdf", make_image_pdf())
    w("ÕÅ¡Æ±Æ.ofd", make_ofd(a, "tags"))
    rec["99260000000000000001"]["duplicates"] = 1
    rec["99260000000000000001"]["issues"] = ["duplicate"]
    return {"records": rec, "unrecognized": ["L_损坏.pdf", "L_损坏.ofd", "M_扫描件.pdf"], "files": files,
            "rules": {"buyer_name": BUYER[0], "buyer_tax_id": BUYER[1]}}


def random_spec(rng: random.Random, i: int):
    seller = rng.choice(SELLERS)
    n_items = rng.randint(1, 3)
    cats = ["*餐饮服务*餐费", "*住宿服务*住宿费", "*文具*笔记本", "*运输服务*客运服务费", "*信息技术服务*技术服务费"]
    items = [(rng.choice(cats), f"{rng.randint(1, 99999)}.{rng.randint(0, 99):02d}", rng.choice([0, 1, 3, 6, 9, 13]))
             for _ in range(n_items)]
    date = f"20{rng.randint(20, 26)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    kind = rng.choice(["增值税专用发票", "普通发票"])
    return make_spec(f"99{rng.randint(0, 10**18 - 1):018d}", date, *seller, items, kind=kind)


if __name__ == "__main__":
    import json
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "samples"
    print(json.dumps(build_sample_set(out), ensure_ascii=False, indent=2))
