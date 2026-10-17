"""fapiao-kit：在本机把 PDF/OFD/XML 电子发票整理成报销包。"""
__version__ = "0.1.0"

from .api import export_xlsx, parse_file, process_for_web, rename, scan, scan_bytes, summary, to_json  # noqa: E402
from .money import to_chinese_upper  # noqa: E402
from .parsers import parse_bytes  # noqa: E402
from .rules import check_records, load_rules  # noqa: E402

__all__ = ["scan", "scan_bytes", "parse_file", "parse_bytes", "rename", "export_xlsx", "summary",
           "to_json", "process_for_web", "check_records", "load_rules", "to_chinese_upper", "__version__"]
