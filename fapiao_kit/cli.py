"""命令行：fapiao scan / rename / export / check。加 --json 输出机器可读结果。"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .api import export_xlsx, rename, scan, summary, to_json
from .rename import DEFAULT_TEMPLATE
from .rules import has_errors, load_rules


def _records(args, exclude=None):
    rules = load_rules(args.rules) if getattr(args, "rules", None) else None
    return scan(args.paths, rules, exclude=exclude)


def _print_table(records):
    for r in records:
        f = r.fields
        if r.recognized:
            print(f"{f.get('date', '?'):10}  {f.get('number', '?'):20}  {f.get('total', '?'):>10}  "
                  f"{(f.get('seller_name') or '?')[:20]:20}  [{'+'.join(x.upper() for x in r.formats)}]")
        else:
            print(f"{'未识别':10}  {r.primary.name}")
        for i in r.issues:
            print(f"    {'✗' if i['level'] == 'error' else '!'} {i['message']}")
    s = summary(records)["totals"]
    print(f"共 {s['count']} 张，价税合计 {s['total']} 元（{s['total_cn']}）"
          + (f"；{s['unrecognized']} 个文件未识别" if s["unrecognized"] else ""))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="fapiao", description="电子发票报销包：本地整理 PDF/OFD/XML 发票")
    p.add_argument("--version", action="version", version=f"fapiao-kit {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("paths", nargs="+", help="发票文件或目录（递归）")
        sp.add_argument("--json", action="store_true", help="输出 JSON")
        sp.add_argument("--rules", help="单位规则文件（TOML），用于抬头/税号检查")

    s = sub.add_parser("scan", help="解析、合并同一张票的多种格式、去重")
    common(s)
    s = sub.add_parser("check", help="按规则检查抬头、税号、跨格式不一致、重复等；有错误时退出码 1")
    common(s)
    s = sub.add_parser("rename", help="把改好名的副本复制到新目录（不动原文件）")
    common(s)
    s.add_argument("-o", "--out", required=True, help="输出目录（必须不存在或为空）")
    s.add_argument("--template", default=DEFAULT_TEMPLATE,
                   help="文件名模板，可用 {date} {seller} {buyer} {total} {amount} {number} {code} {category}")
    s = sub.add_parser("export", help="导出 Excel 汇总表")
    common(s)
    s.add_argument("-o", "--out", required=True, help="输出 .xlsx 路径")

    args = p.parse_args(argv)
    try:
        if args.cmd == "rename":
            out = os.path.abspath(args.out)
            for src in args.paths:
                if os.path.abspath(src) == out:
                    raise ValueError("输出目录不能和输入目录相同")
            records = _records(args, exclude=out)
            items = rename(records, args.out, args.template)
            if args.json:
                print(json.dumps({"renamed": items, **summary(records)}, ensure_ascii=False, indent=2))
            else:
                for it in items:
                    print(f"{it['source_name']}  ->  {it['target']}")
                print(f"已复制 {len(items)} 个文件到 {args.out}，原文件未改动")
            return 0
        records = _records(args)
        if args.cmd == "export":
            export_xlsx(records, args.out)
            if args.json:
                print(json.dumps({"xlsx": args.out, **summary(records)}, ensure_ascii=False, indent=2))
            else:
                _print_table(records)
                print(f"已导出 {args.out}")
            return 0
        if args.json:
            print(to_json(records))
        else:
            _print_table(records)
        if args.cmd == "check" and has_errors(records):
            return 1
        return 0
    except (FileExistsError, ValueError, OSError) as e:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            print(f"错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
