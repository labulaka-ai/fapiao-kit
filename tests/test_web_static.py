"""网页版的静态检查（不需要浏览器）。"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_csp_blocks_external():
    html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    csp = re.search(r'Content-Security-Policy"\s+content="([^"]+)"', html)[1]
    assert "connect-src 'self'" in csp and "default-src 'self'" in csp
    assert "http" not in csp


def test_web_core_file_list_in_sync():
    js = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    listed = set(re.findall(r'"(\w+\.py)"', js.split("CORE_FILES", 1)[1].split("];", 1)[0]))
    actual = {f for f in os.listdir(os.path.join(ROOT, "fapiao_kit")) if f.endswith(".py")}
    assert listed == actual
