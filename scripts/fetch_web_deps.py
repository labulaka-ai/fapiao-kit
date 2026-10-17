"""下载网页版运行所需的第三方文件到 web/vendor/（不入库，已 .gitignore）。

- Pyodide（MPL-2.0）核心：浏览器里的 Python 运行时
- pypdf（BSD-3-Clause）纯 Python wheel：PDF 文字提取

两个文件都按固定版本和 SHA-256 校验，下载后网页完全从本站加载，不再访问任何外部地址。
用法：python scripts/fetch_web_deps.py
"""
from __future__ import annotations

import hashlib
import io
import os
import sys
import tarfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "web", "vendor")
PYODIDE = ("https://registry.npmjs.org/pyodide/-/pyodide-314.0.7.tgz",
           "66b7949e5a0cba2250b586d7e368bf12fb482800748d182c4618254b685ffaa0")
PYPDF = ("https://files.pythonhosted.org/packages/f4/64/5cea5792cae22892a4ddba8ed9f7424c77b4cb49fdca5016bd62145c12c6/pypdf-6.21.0-py3-none-any.whl",
         "3aec619699dacb1b73f57e87d9adaa4424814517b2cc028de20adba5a37af4c4")
PYODIDE_FILES = ["pyodide.js", "pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm",
                 "python_stdlib.zip", "pyodide-lock.json"]


def fetch(url: str, sha: str) -> bytes:
    print("下载", url)
    with urllib.request.urlopen(url, timeout=120) as r:
        data = r.read()
    got = hashlib.sha256(data).hexdigest()
    if got != sha:
        sys.exit(f"SHA-256 不匹配：{url}\n  期望 {sha}\n  实际 {got}")
    return data


def main() -> None:
    os.makedirs(os.path.join(VENDOR, "pyodide"), exist_ok=True)
    tgz = fetch(*PYODIDE)
    with tarfile.open(fileobj=io.BytesIO(tgz)) as t:
        for name in PYODIDE_FILES:
            data = t.extractfile(f"package/{name}").read()
            with open(os.path.join(VENDOR, "pyodide", name), "wb") as f:
                f.write(data)
    with open(os.path.join(VENDOR, "pypdf.whl"), "wb") as f:
        f.write(fetch(*PYPDF))
    print("完成：", VENDOR)


if __name__ == "__main__":
    main()
