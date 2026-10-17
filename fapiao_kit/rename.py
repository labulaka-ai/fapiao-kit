"""按模板给发票改名。只生成副本（目录或 zip），从不改动、移动或删除原文件。"""
from __future__ import annotations

import io
import os
import re
import shutil
import zipfile

from .model import Record

DEFAULT_TEMPLATE = "{date}_{seller}_{total}元_{number}"
_BAD = re.compile(r'[\\/:*?"<>|\s\x00-\x1f]+')


def _safe(s: str, limit: int = 40) -> str:
    s = _BAD.sub("_", s).strip("._")
    return s[:limit] or "未知"


def plan(records: list[Record], template: str = DEFAULT_TEMPLATE) -> list[dict]:
    """返回 [{source_name, source_path, target, record, kind}]，kind: invoice / unrecognized。重复文件不复制。"""
    out, used = [], set()

    def unique(name: str) -> str:
        base, ext = os.path.splitext(name)
        cand, i = name, 2
        while cand.lower() in used:
            cand = f"{base}-{i}{ext}"
            i += 1
        used.add(cand.lower())
        return cand

    for r in records:
        if not r.recognized:
            for d in r.sources:
                out.append({"source_name": d.name, "source_path": d.path,
                            "target": unique("未识别/" + _safe(os.path.basename(d.name), 80)),
                            "record": r.key, "kind": "unrecognized"})
            continue
        f = r.fields
        stem = template.format(
            date=f.get("date") or "无日期", seller=_safe(f.get("seller_name") or "未知销售方", 30),
            buyer=_safe(f.get("buyer_name") or "未知购买方", 30), total=f.get("total") or "0.00",
            amount=f.get("amount") or "", number=f.get("number") or "", code=f.get("code") or "",
            category=_safe(f.get("category") or "其他", 20))
        stem = _safe(stem, 120)
        for d in r.sources:
            out.append({"source_name": d.name, "source_path": d.path, "target": unique(f"{stem}.{d.fmt}"),
                        "record": r.key, "kind": "invoice"})
    return out


def copy_to_dir(records: list[Record], out_dir: str, template: str = DEFAULT_TEMPLATE) -> list[dict]:
    items = plan(records, template)
    if os.path.exists(out_dir) and os.listdir(out_dir):
        raise FileExistsError(f"输出目录不是空的：{out_dir}（为避免覆盖，请换一个新目录）")
    for it in items:
        dst = os.path.join(out_dir, it["target"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(it["source_path"], dst)
        it["target_path"] = dst
    return items


def build_zip(records: list[Record], data_by_name: dict, template: str = DEFAULT_TEMPLATE,
              extra: dict | None = None) -> tuple[bytes, list[dict]]:
    """浏览器用：data_by_name 为 {文件名: 字节}。extra 为额外放进 zip 的 {路径: 字节}（如汇总表）。"""
    items = plan(records, template)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for it in items:
            z.writestr(it["target"], data_by_name[it["source_name"]])
        for k, v in (extra or {}).items():
            z.writestr(k, v)
    return buf.getvalue(), items
