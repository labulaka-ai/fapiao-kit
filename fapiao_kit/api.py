"""Python API。CLI 与网页（Pyodide）都调用这里。"""
from __future__ import annotations

import json
import os

from . import __version__
from .export import build_xlsx, totals
from .merge import merge_docs
from .model import Doc, Record
from .parsers import SUPPORTED, parse_bytes
from .rename import DEFAULT_TEMPLATE, build_zip, copy_to_dir
from .rules import check_records


def iter_files(paths: list[str], exclude: str | None = None) -> list[str]:
    out = []
    ex = os.path.abspath(exclude) if exclude else None
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if not d.startswith(".")
                                 and (ex is None or os.path.abspath(os.path.join(root, d)) != ex))
                for f in sorted(files):
                    if f.lower().endswith(SUPPORTED):
                        out.append(os.path.join(root, f))
        elif os.path.isfile(p):
            out.append(p)
    return out


def parse_file(path: str) -> Doc:
    with open(path, "rb") as f:
        data = f.read()
    return parse_bytes(os.path.basename(path), data, path=path)


def scan(paths, rules: dict | None = None, exclude: str | None = None) -> list[Record]:
    """解析 → 合并去重 → 规则检查。paths 可以是文件或目录（递归）。"""
    if isinstance(paths, str):
        paths = [paths]
    docs = [parse_file(p) for p in iter_files(list(paths), exclude)]
    return check_records(merge_docs(docs), rules)


def scan_bytes(files: list[tuple[str, bytes]], rules: dict | None = None) -> list[Record]:
    docs = [parse_bytes(n, d) for n, d in files if n.lower().endswith(SUPPORTED)]
    return check_records(merge_docs(docs), rules)


def summary(records: list[Record]) -> dict:
    """与 CLI --json 输出相同的结构。"""
    return {
        "tool": "fapiao-kit", "version": __version__,
        "totals": totals(records),
        "records": [r.to_dict() for r in records],
    }


def to_json(records: list[Record], strip_paths: bool = False) -> str:
    data = summary(records)
    if strip_paths:
        for r in data["records"]:
            for d in r["sources"] + r["duplicates"]:
                d["path"] = None
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def export_xlsx(records: list[Record], out_path: str) -> str:
    with open(out_path, "wb") as f:
        f.write(build_xlsx(records))
    return out_path


def rename(records: list[Record], out_dir: str, template: str = DEFAULT_TEMPLATE) -> list[dict]:
    return copy_to_dir(records, out_dir, template)


def process_for_web(files: list[tuple[str, bytes]], rules: dict | None = None,
                    template: str = DEFAULT_TEMPLATE) -> dict:
    """网页一次拿全：JSON 文本、Excel 字节、改名后的 zip 字节（zip 内附带汇总表）。"""
    records = scan_bytes(files, rules)
    xlsx = build_xlsx(records)
    data = dict(files)
    zbytes, items = build_zip(records, data, template, extra={"发票汇总.xlsx": xlsx})
    return {"json": to_json(records, strip_paths=True), "xlsx": xlsx, "zip": zbytes, "renamed": items}
