"""CLI：每个命令的退出码与 JSON 结构；Python API 与 CLI 输出一致。"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cli(*args):
    p = subprocess.run([sys.executable, "-m", "fapiao_kit.cli", *args], cwd=ROOT, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def _rules(tmp_path, truth):
    p = tmp_path / "rules.toml"
    p.write_text(f'buyer_name = "{truth["rules"]["buyer_name"]}"\nbuyer_tax_id = "{truth["rules"]["buyer_tax_id"]}"\n',
                 encoding="utf-8")
    return str(p)


def test_scan_json_schema(sample_set):
    d, truth = sample_set
    code, out, _ = cli("scan", d, "--json")
    assert code == 0
    data = json.loads(out)
    assert data["tool"] == "fapiao-kit" and set(data["totals"]) >= {"count", "amount", "tax", "total", "total_cn"}
    assert data["totals"]["count"] == len(truth["records"])
    for r in data["records"]:
        assert set(r) >= {"key", "recognized", "fields", "formats", "sources", "duplicates", "mismatches", "warnings", "issues"}


def test_check_exit_codes(sample_set, tmp_path):
    d, truth = sample_set
    rules = _rules(tmp_path, truth)
    code, out, _ = cli("check", d, "--rules", rules, "--json")
    assert code == 1  # 样本集里故意放了抬头错、税号错、不一致
    data = json.loads(out)
    errs = {i["rule"] for r in data["records"] for i in r["issues"] if i["level"] == "error"}
    assert {"buyer_name", "buyer_tax_id", "mismatch", "unrecognized"} <= errs
    code, out, _ = cli("check", os.path.join(d, "A_发票.xml"), os.path.join(d, "B.xml"), "--rules", rules)
    assert code == 0, out


def test_export_and_rename(sample_set, tmp_path):
    d, _ = sample_set
    x = tmp_path / "s.xlsx"
    code, out, _ = cli("export", d, "-o", str(x), "--json")
    assert code == 0 and x.exists() and json.loads(out)["xlsx"] == str(x)
    o = tmp_path / "renamed"
    code, out, _ = cli("rename", d, "-o", str(o), "--json")
    assert code == 0 and len(json.loads(out)["renamed"]) == sum(len(f) for _, _, f in os.walk(o))
    code, out, err = cli("rename", d, "-o", str(o))  # 目录非空 → 拒绝
    assert code == 2 and "不是空的" in err
    code, out, err = cli("rename", d, "-o", d)
    assert code == 2


def test_human_output(sample_set):
    d, _ = sample_set
    code, out, _ = cli("scan", d)
    assert code == 0 and "价税合计" in out and "未识别" in out


def test_api_matches_cli(sample_set):
    import fapiao_kit
    d, _ = sample_set
    _, out, _ = cli("scan", d, "--json")
    assert json.loads(out) == json.loads(fapiao_kit.to_json(fapiao_kit.scan(d)))
