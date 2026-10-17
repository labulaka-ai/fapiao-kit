"""三种格式的解析：XML（数电票原件）、OFD、文字型 PDF。全部只读、离线。"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
import xml.etree.ElementTree as ET

from .layout import extract_fields
from .model import Doc, norm_date, norm_digits, norm_name, norm_tax_id
from .money import fmt, to_decimal

SUPPORTED = (".xml", ".ofd", ".pdf")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def normalize_fields(raw: dict) -> dict:
    out = {}
    for k, v in raw.items():
        if v is None or v == "":
            continue
        if k in ("number", "code"):
            v = norm_digits(v)
        elif k == "date":
            v = norm_date(v)
        elif k in ("seller_name", "buyer_name"):
            v = norm_name(v)
        elif k in ("seller_tax_id", "buyer_tax_id"):
            v = norm_tax_id(v)
        elif k in ("amount", "tax", "total"):
            v = fmt(to_decimal(v))
        elif isinstance(v, str):
            v = v.strip()
        if v:
            out[k] = v
    return out


# ---------------------------------------------------------------- XML
XML_MAP = {
    "number": ["InvoiceNumber", "InvoiceNo", "EInvoiceNumber"],
    "code": ["InvoiceCode"],
    "date": ["IssueTime", "IssueDate", "RequestTime"],
    "seller_name": ["SellerName"],
    "seller_tax_id": ["SellerIdNum", "SellerTaxID", "SellerTaxId"],
    "buyer_name": ["BuyerName"],
    "buyer_tax_id": ["BuyerIdNum", "BuyerTaxID", "BuyerTaxId"],
    "amount": ["TotalAmWithoutTax", "TotalAmount", "TaxExclusiveTotalAmount"],
    "tax": ["TotalTaxAm", "TotalTaxAmount", "TaxTotalAmount"],
    "total": ["TotalTax-includedAmount", "TaxInclusiveTotalAmount"],
    "total_cn": ["TotalTax-includedAmountInChinese"],
}


def parse_xml(data: bytes, doc: Doc) -> None:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        doc.error = f"XML 无法解析：{e}"
        return
    first: dict[str, str] = {}
    for el in root.iter():
        name = _local(el.tag)
        if name not in first and el.text and el.text.strip():
            first[name] = el.text.strip()
    raw = {}
    for key, names in XML_MAP.items():
        for n in names:
            if n in first:
                raw[key] = first[n]
                doc.field_sources[key] = "xml"
                break
    for el in root.iter():
        if _local(el.tag) == "IssuItemInformation":
            item = {_local(c.tag): (c.text or "").strip() for c in el}
            doc.items.append({"name": item.get("ItemName", ""), "amount": fmt(to_decimal(item.get("Amount"))),
                              "tax_rate": item.get("TaxRate"), "tax": fmt(to_decimal(item.get("ComTaxAm")))})
    if doc.items and doc.items[0]["name"]:
        m = re.match(r"\*([^*]+)\*", doc.items[0]["name"])
        if m:
            raw["category"] = m[1]
            doc.field_sources["category"] = "xml"
    for el in root.iter():
        if _local(el.tag) == "LabelName" and el.text and "发票" in el.text:
            raw["invoice_type"] = el.text.strip()
            doc.field_sources["invoice_type"] = "xml"
            break
    if "number" not in raw:
        doc.error = "XML 中没有找到发票号码，可能不是电子发票 XML"
    doc.fields = normalize_fields(raw)


# ---------------------------------------------------------------- OFD
OFD_TAG_MAP = {
    "InvoiceNo": "number", "InvoiceCode": "code", "IssueDate": "date",
    "BuyerName": "buyer_name", "BuyerTaxID": "buyer_tax_id",
    "SellerName": "seller_name", "SellerTaxID": "seller_tax_id",
    "TaxExclusiveTotalAmount": "amount", "TaxTotalAmount": "tax",
    "TaxInclusiveTotalAmount": "total",
}
OFD_CUSTOMDATA_MAP = {
    "发票号码": "number", "发票代码": "code", "开票日期": "date",
    "合计金额": "amount", "合计税额": "tax", "价税合计": "total",
    "购买方纳税人识别号": "buyer_tax_id", "销售方纳税人识别号": "seller_tax_id",
    "购买方名称": "buyer_name", "销售方名称": "seller_name",
}


def _zip_path(base: str, loc: str) -> str:
    loc = loc.strip().replace("\\", "/")
    if loc.startswith("/"):
        return loc.lstrip("/")
    parts = [p for p in base.split("/")[:-1] if p] + loc.split("/")
    out = []
    for p in parts:
        if p == "..":
            if out:
                out.pop()
        elif p and p != ".":
            out.append(p)
    return "/".join(out)


def _floats(s: str | None) -> list[float]:
    if not s:
        return []
    vals, toks = [], s.split()
    i = 0
    while i < len(toks):  # DeltaX 支持 "g n v" 缩写
        if toks[i] == "g" and i + 2 < len(toks):
            vals += [float(toks[i + 2])] * int(float(toks[i + 1]))
            i += 3
        else:
            try:
                vals.append(float(toks[i]))
            except ValueError:
                pass
            i += 1
    return vals


def _ofd_text_objects(z: zipfile.ZipFile, path: str):
    """返回 [(id, x, y, x_end, text, size)]，坐标单位 mm，y 自上而下。"""
    out = []
    try:
        root = ET.fromstring(z.read(path))
    except (KeyError, ET.ParseError):
        return out
    for el in root.iter():
        if _local(el.tag) != "TextObject":
            continue
        b = _floats(el.get("Boundary"))
        bx, by = (b[0], b[1]) if len(b) >= 2 else (0.0, 0.0)
        size = float(el.get("Size") or 3.0)
        for tc in el:
            if _local(tc.tag) != "TextCode":
                continue
            txt = tc.text or ""
            x = bx + float(tc.get("X") or 0)
            y = by + float(tc.get("Y") or 0)
            dx = _floats(tc.get("DeltaX"))
            width = sum(dx[: max(len(txt) - 1, 0)]) + size if dx else len(txt) * size
            out.append((el.get("ID"), x, y, x + width, txt, size))
    return out


def parse_ofd(data: bytes, doc: Doc) -> None:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        ofd = ET.fromstring(z.read("OFD.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        doc.error = f"OFD 文件打不开，可能已损坏（{e.__class__.__name__}）"
        return
    raw: dict = {}
    docroot = None
    for el in ofd.iter():
        n = _local(el.tag)
        if n == "DocRoot" and el.text:
            docroot = _zip_path("OFD.xml", el.text)
        elif n == "CustomData":
            key = OFD_CUSTOMDATA_MAP.get((el.get("Name") or "").strip())
            if key and el.text and el.text.strip() and key not in raw:
                raw[key] = el.text.strip()
                doc.field_sources[key] = "ofd-customdata"
    if not docroot:
        doc.error = "OFD 缺少 DocRoot"
        return
    try:
        droot = ET.fromstring(z.read(docroot))
    except (KeyError, ET.ParseError):
        doc.error = "OFD 的 Document.xml 无法读取"
        return
    page_w, page_h = 210.0, 140.0
    content_files, tags_loc = [], None
    for el in droot.iter():
        n = _local(el.tag)
        if n == "PhysicalBox" and el.text:
            v = _floats(el.text)
            if len(v) == 4:
                page_w, page_h = v[2], v[3]
        elif n in ("Page", "TemplatePage") and el.get("BaseLoc"):
            content_files.append(_zip_path(docroot, el.get("BaseLoc")))
        elif n == "CustomTags" and el.text:
            tags_loc = _zip_path(docroot, el.text)
    objs = []
    for cf in content_files:
        objs += _ofd_text_objects(z, cf)
    by_id: dict[str, list[str]] = {}
    for oid, *_rest in objs:
        by_id.setdefault(oid, []).append(_rest[3])

    # 1) 自定义标签：字段 -> TextObject ID
    if tags_loc:
        tag_files = []
        try:
            troot = ET.fromstring(z.read(tags_loc))
            for el in troot.iter():
                if _local(el.tag) == "FileLoc" and el.text:
                    tag_files.append(_zip_path(tags_loc, el.text))
        except (KeyError, ET.ParseError):
            pass
        for tf in tag_files:
            try:
                tr = ET.fromstring(z.read(tf))
            except (KeyError, ET.ParseError):
                continue
            for el in tr.iter():
                key = OFD_TAG_MAP.get(_local(el.tag))
                if not key:
                    continue
                refs = [r.text.strip() for r in el.iter() if _local(r.tag) == "ObjectRef" and r.text]
                val = "".join("".join(by_id.get(r, [])) for r in refs).strip()
                if val:
                    raw[key] = val
                    doc.field_sources[key] = "ofd-tag"

    # 2) 版面兜底
    tokens = [(x, y, xe, t, s) for _, x, y, xe, t, s in objs if t.strip()]
    lf, items, text = extract_fields(tokens, page_w, page_h)
    for k, v in lf.items():
        if k not in raw:
            raw[k] = v
            doc.field_sources[k] = "layout"
    doc.items = items
    if not tokens:
        doc.warnings.append("OFD 中没有文字对象，需人工录入")
    doc.fields = normalize_fields(raw)


# ---------------------------------------------------------------- PDF
def parse_pdf(data: bytes, doc: Doc) -> None:
    try:
        import logging
        logging.getLogger("pypdf").setLevel(logging.CRITICAL)
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = list(reader.pages)
    except Exception as e:  # pypdf 对损坏文件抛出多种异常
        doc.error = f"PDF 文件打不开，可能已损坏（{e.__class__.__name__}）"
        return
    tokens = []
    offset, width, height = 0.0, 595.0, 842.0
    for page in pages:
        box = page.mediabox
        width, height = float(box.width), float(box.height)

        def visit(text, cm, tm, font_dict, font_size, _off=offset, _h=height):
            if not text or not text.strip():
                return
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            scale = (abs(tm[0] * cm[0]) or 1.0)
            size = (font_size or 10) * scale
            t = text.replace("\n", "")
            w = sum(size if ord(c) > 0x2E80 else size * 0.5 for c in t)
            tokens.append((x, _off + (_h - y), x + w, t, size))
        try:
            page.extract_text(visitor_text=visit)
        except Exception as e:
            doc.warnings.append(f"第 {pages.index(page) + 1} 页文字提取失败：{e.__class__.__name__}")
        offset += height
    if not tokens:
        doc.warnings.append("PDF 中没有可提取的文字（可能是扫描件或图片），需人工录入")
        return
    lf, items, text = extract_fields(tokens, width, height)
    for k in lf:
        doc.field_sources[k] = "layout"
    doc.items = items
    doc.fields = normalize_fields(lf)


# ---------------------------------------------------------------- 入口
def parse_bytes(name: str, data: bytes, path: str | None = None) -> Doc:
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    doc = Doc(name=name, fmt=ext, sha256=hashlib.sha256(data).hexdigest(), path=path)
    try:
        if ext == "xml":
            parse_xml(data, doc)
        elif ext == "ofd":
            parse_ofd(data, doc)
        elif ext == "pdf":
            parse_pdf(data, doc)
        else:
            doc.error = "不支持的文件类型"
    except Exception as e:  # 单个坏文件不能拖垮整批
        doc.error = f"解析出错：{e.__class__.__name__}: {e}"
    if not doc.error and not doc.fields.get("number") and not any(w.endswith("需人工录入") for w in doc.warnings):
        doc.warnings.append("没有识别出发票号码，需人工核对")
    return doc
