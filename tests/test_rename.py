"""改名：只复制、不动原文件；模板生效；重名加序号；重复不复制；未识别单独放。"""
import hashlib
import os

import pytest

import fapiao_kit
from fapiao_kit.rename import plan


def _hashes(d):
    out = {}
    for root, _, files in os.walk(d):
        for f in files:
            p = os.path.join(root, f)
            out[os.path.relpath(p, d)] = (hashlib.sha256(open(p, "rb").read()).hexdigest(), os.stat(p).st_mtime_ns)
    return out


def test_rename_copies_and_keeps_originals(sample_set, tmp_path):
    d, truth = sample_set
    before = _hashes(d)
    recs = fapiao_kit.scan(d, truth["rules"])
    out = tmp_path / "out"
    items = fapiao_kit.rename(recs, str(out))
    assert _hashes(d) == before  # 原文件内容和修改时间都不变
    names = sorted(os.path.relpath(os.path.join(r, f), out) for r, _, fs in os.walk(out) for f in fs)
    assert len(names) == len(items)
    assert "2026-03-05_虚构餐饮管理有限公司_300.00元_99260000000000000001.xml" in names
    assert "2026-03-05_虚构餐饮管理有限公司_300.00元_99260000000000000001.ofd" in names
    assert "2026-03-05_虚构餐饮管理有限公司_300.00元_99260000000000000001.pdf" in names
    assert "2026-03-12_示例图书（北京）有限公司_88.00元_99260000000000000004.ofd" in names
    # 重复文件不复制：E 只出现一次，A 的 OFD 只出现一次
    assert sum("99260000000000000005" in n for n in names) == 1
    assert sum(n.endswith("99260000000000000001.ofd") for n in names) == 1
    assert sorted(n for n in names if n.startswith("未识别")) == sorted(
        os.path.join("未识别", n) for n in truth["unrecognized"])
    # 复制内容与原文件逐字节相同
    src = {it["target"]: it["source_path"] for it in items}
    for t, s in src.items():
        assert open(os.path.join(out, t), "rb").read() == open(s, "rb").read()


def test_refuses_non_empty_output(sample_set, tmp_path):
    d, _ = sample_set
    out = tmp_path / "busy"
    out.mkdir()
    (out / "keep.txt").write_text("x")
    with pytest.raises(FileExistsError):
        fapiao_kit.rename(fapiao_kit.scan(d), str(out))
    assert (out / "keep.txt").read_text() == "x"


def test_custom_template_and_collisions():
    from fapiao_kit.merge import merge_docs
    from fapiao_kit.model import Doc
    base = {"date": "2026-01-02", "seller_name": "示例/有限:公司", "total": "10.00"}
    docs = [Doc("a.pdf", "pdf", "1", fields={**base, "number": "99000000000000000001"}),
            Doc("b.pdf", "pdf", "2", fields={**base, "number": "99000000000000000002"})]
    items = plan(merge_docs(docs), "{date}_{seller}_{total}")
    assert [i["target"] for i in items] == ["2026-01-02_示例_有限_公司_10.00.pdf", "2026-01-02_示例_有限_公司_10.00-2.pdf"]


def test_zip_for_web(sample_set):
    import io
    import zipfile
    d, truth = sample_set
    files = [(n, open(os.path.join(d, n), "rb").read()) for n in sorted(os.listdir(d))]
    res = fapiao_kit.process_for_web(files, truth["rules"])
    z = zipfile.ZipFile(io.BytesIO(res["zip"]))
    names = z.namelist()
    assert "发票汇总.xlsx" in names
    assert len(names) == len(res["renamed"]) + 1
