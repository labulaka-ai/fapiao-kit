"""合并与去重：三件套合一、以 XML 为准、重复只计一次、同日同额不同号不误合、坏文件单列。"""


def test_record_count(records, sample_set):
    _, truth = sample_set
    keys = [k for k, r in records.items() if r.recognized]
    assert sorted(keys) == sorted(truth["records"])
    assert sorted(r.primary.name for r in records.values() if not r.recognized) == sorted(truth["unrecognized"])


def test_formats_duplicates_mismatches(records, sample_set):
    _, truth = sample_set
    for key, exp in truth["records"].items():
        r = records[key]
        assert r.formats == exp["formats"], key
        assert len(r.duplicates) == exp["duplicates"], key
        assert [m["field"] for m in r.mismatches] == exp["mismatch"], key
        for f, v in exp["fields"].items():
            assert r.fields.get(f) == v, (key, f)


def test_triple_merged_with_xml_primary(records):
    r = records["99260000000000000001"]
    assert r.primary.fmt == "xml"
    assert {d.fmt for d in r.sources} == {"xml", "ofd", "pdf"}
    assert r.duplicates[0].name == "ÕÅ¡Æ±Æ.ofd"


def test_xml_wins_on_mismatch(records):
    r = records["99260000000000000006"]
    assert r.fields["total"] == "200.00"
    assert r.mismatches == [{"field": "total", "label": "价税合计", "values": {"xml": "200.00", "pdf": "300.00"}}]
    assert any("以 XML 为准" in w for w in r.warnings)


def test_same_day_same_amount_not_merged(records):
    e, k = records["99260000000000000005"], records["99260000000000000009"]
    assert e.fields["date"] == k.fields["date"] and e.fields["total"] == k.fields["total"]
    assert e is not k and not k.duplicates


def test_exact_duplicate_detected_by_hash(records):
    r = records["99260000000000000005"]
    assert r.duplicates[0].sha256 == r.sources[0].sha256
    assert any("内容完全相同" in w for w in r.warnings)


def test_suspect_duplicate_without_number():
    from fapiao_kit.merge import merge_docs
    from fapiao_kit.model import Doc
    a = Doc("a.pdf", "pdf", "1", fields={"number": "99000000000000000077", "date": "2026-01-01", "total": "10.00"})
    b = Doc("b.pdf", "pdf", "2", fields={"date": "2026-01-01", "total": "10.00"})
    recs = merge_docs([a, b])
    assert len(recs) == 2
    assert any("疑似" in w for w in recs[1].warnings) and not recs[1].recognized
