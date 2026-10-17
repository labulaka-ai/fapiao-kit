---
name: fapiao-kit
description: >-
  电子发票报销包：在本机把一堆 PDF / OFD / XML 数电票（含旧版增值税电子发票）整理成报销材料。
  同一张票的几种格式合成一条（以 XML 为准，不一致时报出）、按号码去重、改名复制到新目录、
  导出 Excel 汇总表（合计 + 大写金额 + 类别小计）、按单位规则检查抬头和税号。
  触发场景：「帮我整理发票 / 报销」「这些发票有没有重复」「把发票按日期金额改名」「出一张发票汇总表」
  「检查发票抬头和税号对不对」。
  不用于：发票真伪查验（需税务平台联网，本工具不做）、图片或扫描件发票（没有文字层，需人工录入）、开具或修改发票。
---

# fapiao-kit（电子发票报销包）

核心原则：**只读不改原文件；发票内容不联网、不上传；认不出的就说认不出，不猜。**

## 准备

- 依赖：`pip install -r requirements.txt`（只有 pypdf，其余为 Python 标准库）。
- 在仓库根目录运行：`python -m fapiao_kit.cli <命令> ...`（`pip install .` 后也可以直接用 `fapiao`）。
- 单位规则文件（可选）：TOML，示例见 `rules/example.toml`（`buyer_name`、`buyer_tax_id`，可选日期范围和类别限额）。
  用户没有提供单位抬头和税号时，询问用户，不要猜，也不要从发票里“推断”本单位抬头。

## 总流程

1. **扫描**：`scan <目录或文件...> --json`。告诉用户：共几张票、价税合计、几个重复文件、几个文件没认出来。
2. **检查**（有单位信息时）：`check <目录> --rules 单位.toml --json`。退出码 1 表示有错误。
   按问题类别汇总：抬头 / 税号不符、不同格式内容不一致、超限额、日期超范围、未识别文件；不要逐条倾倒。
3. **请用户确认**有问题的票怎么处理（例如抬头错的票要找商家重开）。工具不替用户决定剔除哪张票。
4. **改名复制**：`rename <目录> -o <新目录>`。新目录必须不存在或为空；原文件不会被改动。
   默认模板 `{date}_{seller}_{total}元_{number}`，可用 `--template` 改。重复文件不复制，未识别的放进 `未识别/`。
5. **导出汇总表**：`export <目录> -o 发票汇总.xlsx`。表里有明细、合计、大写金额、张数、按类别小计和“需处理”清单。

## JSON 输出要点

- `totals`：`count`（已识别张数）、`amount` / `tax` / `total`（字符串，两位小数）、`total_cn`（大写）、`unrecognized`。
- `records[]`：`key`（号码；旧版为 `代码-号码`）、`recognized`、`fields`、`formats`（如 `["xml","ofd","pdf"]`）、
  `duplicates`、`mismatches`（`{field, label, values: {xml: ..., pdf: ...}}`）、`issues`（`{level, rule, message}`）。
- `fields` 字段：`number` `code` `date`（YYYY-MM-DD）`invoice_type` `seller_name` `seller_tax_id`
  `buyer_name` `buyer_tax_id` `amount` `tax` `total` `total_cn` `category`。

## Python API

```python
import fapiao_kit as fk
records = fk.scan("发票目录", rules={"buyer_name": "示例大学", "buyer_tax_id": "99TEST000000000001"})
fk.export_xlsx(records, "发票汇总.xlsx")
fk.rename(records, "改名后")
print(fk.to_json(records))
```

## Operating Rules

1. 不改动、不移动、不删除用户的原始发票文件；`rename` 只复制到新目录。
2. 不上传、不联网；不要把发票内容（号码、税号、金额、姓名）贴到外部服务或 issue 里。
3. 不一致时以 XML 为准，但必须把不一致告诉用户，不要静默采用。
4. `recognized: false` 的文件如实告诉用户“需要人工录入”，不要猜字段值。
5. 本工具不做真伪查验；用户问“是不是真票”时，指引其到国家税务总局全国增值税发票查验平台自行查验。
6. 不生成、不修改发票票面；`tests/gen/` 只生成标有“测试样例 非真实发票”的合成样本，仅用于测试。
