// 发票报销包网页版：在浏览器里用 Pyodide 运行和命令行完全相同的 Python 核心（../fapiao_kit/）。
// 页面加载完以后不会再发出任何网络请求；所有文件只在浏览器内存中处理。
"use strict";

const CORE_FILES = ["__init__.py", "api.py", "cli.py", "export.py", "layout.py", "merge.py",
  "model.py", "money.py", "parsers.py", "rename.py", "rules.py", "xlsx.py"];
const $ = (id) => document.getElementById(id);
let py = null;
let outputs = null;

async function boot() {
  try {
    py = await loadPyodide({ indexURL: "vendor/pyodide/" });
    const site = py.runPython("import site; site.getsitepackages()[0]");
    const whl = await (await fetch("vendor/pypdf.whl")).arrayBuffer();
    py.unpackArchive(whl, "zip", { extractDir: site });
    py.FS.mkdirTree("/home/pyodide/fapiao_kit");
    for (const f of CORE_FILES) {
      const r = await fetch("../fapiao_kit/" + f);
      if (!r.ok) throw new Error("缺少文件 " + f);
      py.FS.writeFile("/home/pyodide/fapiao_kit/" + f, await r.text());
    }
    py.runPython("import sys; sys.path.insert(0, '/home/pyodide'); import fapiao_kit, fapiao_kit.api");
    $("dropText").textContent = "把发票文件（或整个文件夹）拖到这里";
    $("drop").classList.add("ready");
    $("pick").disabled = false;
    document.body.dataset.ready = "1";
  } catch (e) {
    $("dropText").textContent = "加载失败：" + e.message + "（如果你是开发者，请先运行 python scripts/fetch_web_deps.py）";
    document.body.dataset.ready = "error";
  }
}

function readEntry(entry, prefix, out) {
  return new Promise((resolve) => {
    if (entry.isFile) {
      entry.file((f) => { out.push({ file: f, name: prefix + f.name }); resolve(); }, () => resolve());
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      const all = [];
      const next = () => reader.readEntries(async (batch) => {
        if (!batch.length) {
          for (const e of all) await readEntry(e, prefix + entry.name + "/", out);
          resolve();
        } else { all.push(...batch); next(); }
      }, () => resolve());
      next();
    } else resolve();
  });
}

async function collect(dt) {
  const out = [];
  const entries = dt.items ? Array.from(dt.items).map((i) => i.webkitGetAsEntry && i.webkitGetAsEntry()) : [];
  if (entries.length && entries.every(Boolean)) {
    for (const e of entries) await readEntry(e, "", out);
  } else {
    for (const f of dt.files) out.push({ file: f, name: f.webkitRelativePath || f.name });
  }
  return out;
}

async function processFiles(list) {
  if (!py) return;
  const ok = list.filter((x) => /\.(pdf|ofd|xml)$/i.test(x.name));
  if (!ok.length) { alert("没有找到 PDF、OFD 或 XML 文件"); return; }
  document.body.dataset.state = "processing";
  $("dropText").textContent = `正在整理 ${ok.length} 个文件…`;
  py.FS.mkdirTree("/tmp/in");
  const seen = new Set();
  const meta = [];
  for (let i = 0; i < ok.length; i++) {
    let name = ok[i].name;
    for (let k = 2; seen.has(name.toLowerCase()); k++) name = ok[i].name.replace(/(\.[^.]+)$/, `-${k}$1`);
    seen.add(name.toLowerCase());
    const buf = new Uint8Array(await ok[i].file.arrayBuffer());
    py.FS.writeFile(`/tmp/in/${i}`, buf);
    meta.push({ name, path: `/tmp/in/${i}` });
  }
  const rules = {};
  const bn = $("buyerName").value.trim(), bt = $("buyerTaxId").value.trim();
  if (bn) rules.buyer_name = bn;
  if (bt) rules.buyer_tax_id = bt;
  py.globals.set("_meta", JSON.stringify({ files: meta, rules }));
  const text = py.runPython(`
import json
from fapiao_kit.api import process_for_web
_m = json.loads(_meta)
_files = [(f["name"], open(f["path"], "rb").read()) for f in _m["files"]]
_res = process_for_web(_files, _m["rules"] or None)
open("/tmp/out.xlsx", "wb").write(_res["xlsx"])
open("/tmp/out.zip", "wb").write(_res["zip"])
_res["json"]
`);
  for (const m of meta) py.FS.unlink(m.path);
  outputs = { xlsx: py.FS.readFile("/tmp/out.xlsx"), zip: py.FS.readFile("/tmp/out.zip"), json: JSON.parse(text) };
  window.__fapiaoResult = outputs.json;  // 供自动化测试读取
  render(outputs.json);
  $("dropText").textContent = "还可以继续拖入（会重新整理全部文件）";
  document.body.dataset.state = "done";
}

function esc(s) { return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

function render(data) {
  const t = data.totals;
  $("summary").textContent = `共 ${t.count} 张发票，价税合计 ${t.total} 元（${t.total_cn}）` +
    (t.unrecognized ? `；另有 ${t.unrecognized} 个文件没能识别，需要你手工处理` : "");
  const rows = data.records.map((r) => {
    const f = r.fields;
    const errs = r.issues.filter((i) => i.level === "error");
    const warns = r.issues.filter((i) => i.level !== "error");
    const cls = errs.length ? "error" : warns.length ? "warn" : "";
    const status = !r.recognized ? "✗ 没认出来" : errs.length ? "✗ 有问题" : r.duplicates.length ? "⚠ 有重复" : warns.length ? "⚠ 请看说明" : "✓ 正常";
    const files = r.sources.map((s) => s.format.toUpperCase()).join("+") + (r.duplicates.length ? `（另有 ${r.duplicates.length} 个重复已跳过）` : "");
    const notes = r.issues.map((i) => i.message).join("；");
    return `<tr class="${cls}" data-key="${esc(r.key)}"><td>${status}</td><td>${esc(f.date)}</td><td>${esc(f.number || r.primary)}</td>` +
      `<td>${esc(f.seller_name)}</td><td class="money">${esc(f.total)}</td><td>${esc(files)}</td><td>${esc(notes)}</td></tr>`;
  });
  document.querySelector("#table tbody").innerHTML = rows.join("");
  $("resultStep").hidden = false;
}

function download(bytes, name, type) {
  const url = URL.createObjectURL(new Blob([bytes], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function init() {
  for (const id of ["buyerName", "buyerTaxId"]) {
    $(id).value = localStorage.getItem("fapiao." + id) || "";
    $(id).addEventListener("input", () => localStorage.setItem("fapiao." + id, $(id).value));
  }
  const drop = $("drop");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", async (e) => { e.preventDefault(); drop.classList.remove("over"); await processFiles(await collect(e.dataTransfer)); });
  $("pick").addEventListener("click", () => $("fileInput").click());
  $("fileInput").addEventListener("change", async (e) => { await processFiles(Array.from(e.target.files).map((f) => ({ file: f, name: f.name }))); e.target.value = ""; });
  $("dlXlsx").addEventListener("click", () => download(outputs.xlsx, "发票汇总.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"));
  $("dlZip").addEventListener("click", () => download(outputs.zip, "改名后的发票.zip", "application/zip"));
  $("reset").addEventListener("click", () => { outputs = null; $("resultStep").hidden = true; document.querySelector("#table tbody").innerHTML = ""; });
  boot();
}
init();
