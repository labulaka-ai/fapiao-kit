"""数据模型：单个文件解析结果（Doc）与合并后的发票记录（Record）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date as _date

FIELDS = [
    "number", "code", "date", "invoice_type", "seller_name", "seller_tax_id",
    "buyer_name", "buyer_tax_id", "amount", "tax", "total", "total_cn", "category",
]
# 跨格式比对的字段（大写金额、类别、票种只作提示，不算不一致）
COMPARE_FIELDS = ["number", "code", "date", "seller_name", "seller_tax_id",
                  "buyer_name", "buyer_tax_id", "amount", "tax", "total"]
FORMAT_PRIORITY = {"xml": 0, "ofd": 1, "pdf": 2}
FIELD_LABELS = {
    "number": "发票号码", "code": "发票代码", "date": "开票日期", "invoice_type": "票种",
    "seller_name": "销售方", "seller_tax_id": "销售方税号", "buyer_name": "购买方",
    "buyer_tax_id": "购买方税号", "amount": "金额", "tax": "税额", "total": "价税合计",
    "total_cn": "价税合计(大写)", "category": "类别",
}


@dataclass
class Doc:
    """一个文件的解析结果。fields 中金额为两位小数字符串，日期为 YYYY-MM-DD。"""
    name: str
    fmt: str
    sha256: str
    fields: dict = field(default_factory=dict)
    field_sources: dict = field(default_factory=dict)  # 字段 -> 'xml' / 'ofd-tag' / 'ofd-customdata' / 'layout'
    items: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    error: str | None = None
    path: str | None = None

    @property
    def key(self) -> str | None:
        num = self.fields.get("number")
        if not num:
            return None
        code = self.fields.get("code")
        return f"{code}-{num}" if code else num

    def to_dict(self) -> dict:
        return {"name": self.name, "path": self.path, "format": self.fmt, "sha256": self.sha256,
                "fields": self.fields, "field_sources": self.field_sources, "items": self.items,
                "warnings": self.warnings, "error": self.error}


@dataclass
class Record:
    """一张发票（同一张票的 XML/OFD/PDF 合为一条）。"""
    key: str
    fields: dict
    primary: Doc
    sources: list            # 参与合并的 Doc（每种格式一份）
    duplicates: list = field(default_factory=list)   # 重复文件 Doc
    mismatches: list = field(default_factory=list)   # [{field, label, values: {fmt: value}}]
    warnings: list = field(default_factory=list)
    recognized: bool = True
    issues: list = field(default_factory=list)       # check 结果 [{level, rule, message}]

    @property
    def formats(self) -> list:
        return sorted({d.fmt for d in self.sources}, key=lambda f: FORMAT_PRIORITY.get(f, 9))

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "recognized": self.recognized,
            "fields": self.fields,
            "formats": self.formats,
            "primary": self.primary.name,
            "sources": [{"name": d.name, "path": d.path, "format": d.fmt, "sha256": d.sha256} for d in self.sources],
            "duplicates": [{"name": d.name, "path": d.path, "format": d.fmt, "sha256": d.sha256} for d in self.duplicates],
            "mismatches": self.mismatches,
            "warnings": self.warnings,
            "issues": self.issues,
            "items": self.primary.items,
        }


def norm_date(s: str | None) -> str | None:
    if not s:
        return None
    m = re.search(r"(\d{4})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})", str(s))
    if not m:
        return None
    try:
        return _date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    except ValueError:
        return None


def norm_name(s: str | None) -> str | None:
    """公司名：去空白，全角括号统一。"""
    if s is None:
        return None
    s = re.sub(r"\s+", "", str(s)).replace("(", "（").replace(")", "）")
    return s or None


def norm_tax_id(s: str | None) -> str | None:
    if s is None:
        return None
    s = re.sub(r"\s+", "", str(s)).upper()
    return s or None


def norm_digits(s: str | None) -> str | None:
    if s is None:
        return None
    s = re.sub(r"\D", "", str(s))
    return s or None
