"""网页版端到端（Playwright + Chromium）：拖拽 → 列表 → 下载 Excel/zip，
并证明处理期间零网络请求、断网可用、结果与命令行逐字段一致。

需要：python scripts/fetch_web_deps.py（下载 Pyodide 与 pypdf 到 web/vendor/）
     playwright install chromium
缺少时自动跳过。
"""
import base64
import functools
import http.server
import io
import json
import os
import re
import threading
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "web", "vendor", "pyodide", "pyodide.asm.wasm")

pytestmark = pytest.mark.skipif(not os.path.exists(VENDOR), reason="web/vendor 缺失：先运行 python scripts/fetch_web_deps.py")


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=ROOT))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # 浏览器未安装
            pytest.skip(f"Chromium 不可用：{e}")
        yield b
        b.close()


@pytest.fixture()
def page(browser, server):
    ctx = browser.new_context(accept_downloads=True)
    log = {"requests": [], "external": []}

    def on_request(req):
        log["requests"].append(req.url)

    def guard(route):  # 任何指向本机以外的请求都记下并拦截
        if not route.request.url.startswith(server):
            log["external"].append(route.request.url)
            return route.abort()
        return route.continue_()
    ctx.route("**/*", guard)
    ctx.on("request", on_request)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(server + "/web/index.html")
    pg.wait_for_function("document.body.dataset.ready", timeout=180_000)
    assert pg.evaluate("document.body.dataset.ready") == "1", pg.text_content("#dropText")
    yield pg, log, ctx, errors
    ctx.close()


def _drop(pg, sample_dir, names):
    payload = [{"name": n, "b64": base64.b64encode(open(os.path.join(sample_dir, n), "rb").read()).decode()} for n in names]
    pg.evaluate("""(files) => {
        const dt = new DataTransfer();
        for (const f of files) {
            const bin = Uint8Array.from(atob(f.b64), c => c.charCodeAt(0));
            dt.items.add(new File([bin], f.name));
        }
        const el = document.getElementById('drop');
        for (const t of ['dragenter', 'dragover', 'drop'])
            el.dispatchEvent(new DragEvent(t, {dataTransfer: dt, bubbles: true, cancelable: true}));
    }""", payload)
    pg.wait_for_function("document.body.dataset.state === 'done'", timeout=120_000)


def _http(urls):
    return [u for u in urls if u.startswith("http")]


def test_drag_drop_full_flow_no_network(page, sample_set, tmp_path):
    pg, log, ctx, errors = page
    d, truth = sample_set
    names = sorted(os.listdir(d))
    pg.fill("#buyerName", truth["rules"]["buyer_name"])
    pg.fill("#buyerTaxId", truth["rules"]["buyer_tax_id"])
    assert log["external"] == []  # 加载阶段也没有访问外部地址
    n_before = len(log["requests"])

    _drop(pg, d, names)
    rows = pg.locator("#table tbody tr")
    assert rows.count() == len(truth["records"]) + len(truth["unrecognized"])
    assert pg.locator("#table tbody tr.error").count() == 3 + len(truth["unrecognized"])  # 抬头、税号、不一致 + 未识别
    assert "共 10 张发票" in pg.text_content("#summary")

    with pg.expect_download() as dl:
        pg.click("#dlXlsx")
    xlsx = tmp_path / "w.xlsx"
    dl.value.save_as(xlsx)
    with pg.expect_download() as dl2:
        pg.click("#dlZip")
    zpath = tmp_path / "w.zip"
    dl2.value.save_as(zpath)

    # 处理 + 下载期间：零 http(s) 请求
    assert _http(log["requests"][n_before:]) == []
    assert log["external"] == []
    assert errors == []

    import openpyxl
    from decimal import Decimal
    ws = openpyxl.load_workbook(xlsx)["汇总"]
    tail = {r[0]: r for r in ws.iter_rows(values_only=True) if isinstance(r[0], str)}
    exp_total = sum(Decimal(r["fields"]["total"]) for r in truth["records"].values())
    assert Decimal(str(tail["合计"][12])).quantize(Decimal("0.01")) == exp_total
    z = zipfile.ZipFile(zpath)
    assert "发票汇总.xlsx" in z.namelist()
    assert "2026-03-05_虚构餐饮管理有限公司_300.00元_99260000000000000001.pdf" in z.namelist()
    assert any(n.startswith("未识别/") for n in z.namelist())


def test_browser_result_equals_cli(page, sample_set):
    """同一批样本：浏览器（Pyodide）输出的 JSON 与本机 Python 输出逐字段相同（版本号等元数据除外）。"""
    import fapiao_kit
    pg, log, ctx, errors = page
    d, truth = sample_set
    names = sorted(os.listdir(d))
    pg.fill("#buyerName", truth["rules"]["buyer_name"])
    pg.fill("#buyerTaxId", truth["rules"]["buyer_tax_id"])
    _drop(pg, d, names)
    web = pg.evaluate("window.__fapiaoResult")
    local = json.loads(fapiao_kit.to_json(fapiao_kit.scan(d, truth["rules"]), strip_paths=True))
    assert web == local


def test_offline_after_load(page, sample_set):
    pg, log, ctx, errors = page
    d, _ = sample_set
    ctx.set_offline(True)
    _drop(pg, d, ["A_发票.xml", "A_发票.pdf", "A_发票.ofd"])
    assert pg.locator("#table tbody tr").count() == 1
    assert "XML+OFD+PDF" in pg.text_content("#table tbody tr")


def test_file_picker_and_settings_persist(page, sample_set, server):
    pg, log, ctx, errors = page
    d, _ = sample_set
    pg.fill("#buyerName", "示例大学")
    pg.set_input_files("#fileInput", [os.path.join(d, "I.xml")])
    pg.wait_for_function("document.body.dataset.state === 'done'")
    assert "示例大字" in pg.text_content("#table tbody")
    pg.reload()
    pg.wait_for_function("document.body.dataset.ready")
    assert pg.input_value("#buyerName") == "示例大学"  # 只存在本地 localStorage


def test_csp_really_blocks_external_fetch(page):
    """反向对照：页面里主动 fetch 外部地址必须失败（被 CSP 拦下，根本发不出去）。"""
    pg, log, ctx, errors = page
    ok = pg.evaluate("""async () => { try { await fetch('https://example.com/x'); return true; } catch (e) { return false; } }""")
    assert ok is False
    assert log["external"] == []
