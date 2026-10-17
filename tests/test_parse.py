"""字段级断言：每个样本文件的每个字段都和生成器的标准答案逐项比对。"""
import os
import random

import pytest

from fapiao_kit import parse_bytes, parse_file
from tests.gen import samples as S

FIELDS = ["number", "code", "date", "invoice_type", "seller_name", "seller_tax_id", "buyer_name",
          "buyer_tax_id", "amount", "tax", "total", "category"]


def _file_truth(truth):
    """文件名 -> 标准答案字段（按样本集的约定）。"""
    by_prefix = {}
    for key, r in truth["records"].items():
        by_prefix[r["fields"]["number"]] = r["fields"]
    return by_prefix


CASES = [  # (文件名, 号码, 预期中被故意改掉的字段)
    ("A_发票.xml", "99260000000000000001", {}), ("A_发票.ofd", "99260000000000000001", {}),
    ("A_发票.pdf", "99260000000000000001", {}), ("ÕÅ¡Æ±Æ.ofd", "99260000000000000001", {}),
    ("B.xml", "99260000000000000002", {}), ("C 住宿.ofd", "99260000000000000003", {}),
    ("D.ofd", "99260000000000000004", {}), ("E 打车.pdf", "99260000000000000005", {}),
    ("E 打车(1).pdf", "99260000000000000005", {}), ("F_旧版.pdf", "99000001", {}),
    ("H.xml", "99260000000000000006", {}), ("H.pdf", "99260000000000000006", {"total": "300.00"}),
    ("I.xml", "99260000000000000007", {}), ("J.pdf", "99260000000000000008", {}),
    ("K.pdf", "99260000000000000009", {}),
]


@pytest.mark.parametrize("name,number,tampered", CASES, ids=[c[0] for c in CASES])
def test_fields_match_ground_truth(sample_set, name, number, tampered):
    d, truth = sample_set
    expected = dict(_file_truth(truth)[number])
    expected.update(tampered)
    doc = parse_file(os.path.join(d, name))
    assert doc.error is None
    for f in FIELDS:
        assert doc.fields.get(f) == expected.get(f), f"{name} 字段 {f}"


def test_xml_items_parsed(sample_set):
    d, _ = sample_set
    doc = parse_file(os.path.join(d, "B.xml"))
    assert [i["name"] for i in doc.items] == ["*纸制品*打印纸", "*文具*中性笔"]
    assert [i["amount"] for i in doc.items] == ["120.00", "35.40"]


def test_ofd_field_sources(sample_set):
    d, _ = sample_set
    tags = parse_file(os.path.join(d, "A_发票.ofd"))
    assert tags.field_sources["number"] == "ofd-tag" and tags.field_sources["buyer_name"] == "ofd-tag"
    custom = parse_file(os.path.join(d, "D.ofd"))
    assert custom.field_sources["number"] == "ofd-customdata" and custom.field_sources["seller_name"] == "layout"
    layout = parse_file(os.path.join(d, "C 住宿.ofd"))
    assert set(layout.field_sources.values()) == {"layout"}


@pytest.mark.parametrize("name,needle", [
    ("L_损坏.pdf", "PDF"), ("L_损坏.ofd", "OFD"), ("M_扫描件.pdf", "需人工录入")])
def test_bad_files_do_not_crash_and_are_flagged(sample_set, name, needle):
    d, _ = sample_set
    doc = parse_file(os.path.join(d, name))
    assert "number" not in doc.fields
    assert needle in (doc.error or "") + "".join(doc.warnings)


def test_unsupported_and_garbage():
    assert parse_bytes("a.txt", b"hello").error
    assert parse_bytes("a.xml", b"<not-closed").error
    assert parse_bytes("a.xml", b"<root><x>1</x></root>").error  # 不是发票 XML


@pytest.mark.parametrize("seed", range(6))
def test_random_roundtrip_all_formats(seed):
    """随机生成字段 → 生成 XML / 3 种 OFD / PDF → 解析 → 必须得到原字段（每个 seed 5 张票 × 5 种文件）。"""
    rng = random.Random(seed)
    for i in range(5):
        spec = S.random_spec(rng, i)
        exp = S.truth(spec)
        for name, data in [("x.xml", S.make_xml(spec)), ("t.ofd", S.make_ofd(spec, "tags")),
                           ("d.ofd", S.make_ofd(spec, "deltax")), ("m.ofd", S.make_ofd(spec, "multiseg")),
                           ("p.pdf", S.make_pdf(spec))]:
            doc = parse_bytes(name, data)
            got = {f: doc.fields.get(f) for f in exp}
            assert got == exp, f"seed={seed} #{i} {name}"


def test_samples_are_marked_as_fake(sample_set):
    """防伪造约束：样本里必须有“测试样例 非真实发票”，号码 99 开头，税号含 TEST。"""
    d, truth = sample_set
    import zipfile
    for name in ["A_发票.xml", "B.xml"]:
        assert S.WATERMARK in open(os.path.join(d, name), encoding="utf-8").read()
    with zipfile.ZipFile(os.path.join(d, "A_发票.ofd")) as z:
        assert S.WATERMARK in z.read("Doc_0/Pages/Page_0/Content.xml").decode()
    from pypdf import PdfReader
    assert S.WATERMARK in PdfReader(os.path.join(d, "A_发票.pdf")).pages[0].extract_text()
    for r in truth["records"].values():
        assert r["fields"]["number"].startswith("99")
        assert "TEST" in r["fields"]["seller_tax_id"] and "TEST" in r["fields"]["buyer_tax_id"]
