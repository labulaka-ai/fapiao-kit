<p align="right"><strong>简体中文</strong> | <a href="README.en.md">English</a></p>

# fapiao-kit · 发票报销包

![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg) ![Local only](https://img.shields.io/badge/发票-不上传-brightgreen) ![Agent Skill](https://img.shields.io/badge/Agent%20Skill-SKILL.md-green) ![Docs](https://img.shields.io/badge/docs-中文%20%7C%20English-orange)

> 作者：**Labulaka**（GitHub [@labulaka-ai](https://github.com/labulaka-ai)）· 公众号「**时空AI深水区**」

[为什么做这个](#为什么我做这个) · [功能](#功能) · [网页版（不用装任何东西）](#网页版给不用命令行的人) · [命令行与-python-api](#命令行与-python-api) · [作为 agent skill](#作为-agent-skill-使用) · [可信度](#可信度测试与验证) · [已知限制](#已知限制)

把一堆 PDF / OFD / XML 电子发票，**在你自己的电脑上**整理成报销材料：同一张票的几种格式合成一条、重复的只算一次、按“日期_销售方_金额_号码”改好名、出一张带合计和大写金额的 Excel 汇总表，顺便检查发票抬头和税号是不是本单位的。

**在线使用（不用装任何东西）：<https://labulaka-ai.github.io/fapiao-kit/>**——打开链接，把发票拖进去就行；文件只在你的浏览器里处理，不会上传。

它有两种用法：**不懂电脑的人**打开一个网页，把发票拖进去，下载 Excel 和改好名的 zip；**开发者和 AI agent** 用命令行、JSON 输出和 Python API。两种用法跑的是**同一份 Python 代码**（网页里用 Pyodide 运行），所以下面的测试同时覆盖两者。

![网页版截图（合成样例）](docs/web-demo.png)

---

## 为什么我做这个

报销整理发票是一件高频、低技术含量、但很容易出错的事，而且做这件事的往往是行政、秘书和文科背景的同学：

- **一张票三个文件**：数电票可以下载成 PDF、OFD、XML 三种格式，手上常常同一张票有好几份，汇总时很容易重复计数；
- **重复报销是审计问题**：电子发票能反复打印，“二次打印重复报销”已经出现在地方预算执行审计里（敖汉旗人民政府，2024-09）；有的高校要求“未经查验的发票不予报销”（中国地质大学（武汉），2025-05）；
- **XML 才是原件**：税务部门答复，只有含数字签名的 XML 能单独报销入账，PDF / OFD 只是版式文件（上海税务热点问答，2023-08）。所以三种格式内容不一致时，应该以 XML 为准，并且要提醒用户；
- **被财务退回**：抬头写错一个字、税号不对，是最常见的退回原因之一。

现有工具里，开源的[发票酱](https://github.com/erma0/fapiao-print)做得很好，但重心是打印排版、桌面版只支持 Windows；商业 App 大多要把发票上传到云端。这个项目只做“报销包”这一件事：**合并、去重、改名、汇总、查抬头**，全程本地，并且每一步都有自动化测试。

## 功能

| 命令 | 作用 |
|---|---|
| `scan` | 解析 XML / OFD / 文字型 PDF，提取发票号码、代码、开票日期、销售方、购买方、税号、金额、税额、价税合计、类别；同一张票的多种格式合为一条（**XML 优先**），各格式间不一致的字段逐项报出；按号码去重 |
| `check` | 按单位规则文件检查：购买方名称 / 税号是否等于本单位、不同格式是否一致、金额 + 税额 = 价税合计、大写金额是否对得上、开票日期范围、单类单张限额、负数发票；有错误时退出码 1 |
| `rename` | 把改好名的**副本**复制到一个新目录（默认 `{date}_{seller}_{total}元_{number}`），重名自动加序号，重复文件不复制，认不出的放进 `未识别/`；**从不改动原文件** |
| `export` | 导出 Excel：明细（发票号码按文本存，不会变成科学计数法）、合计、**中文大写金额**、张数、按类别小计、“需处理”清单 |

所有命令都支持 `--json`。

**认不出来的就说认不出来**：扫描件 / 图片型 PDF（没有文字层）、损坏文件会单独列出，标“需人工录入”，不会乱填数字。

## 网页版：给不用命令行的人

**直接打开：<https://labulaka-ai.github.io/fapiao-kit/>**（由 GitHub Pages 托管，部署流程见 `.github/workflows/pages.yml`）。

`web/index.html` 是一个静态网页，三步：① 填一次本单位抬头和税号（只存在本机浏览器里）→ ② 把发票文件或整个文件夹拖进去 → ③ 下载“汇总表 Excel”和“改好名的发票 zip”（zip 里也附了汇总表）。有问题的票标红，并用一句大白话说明原因。

- **不上传**：页面用 Content-Security-Policy 禁止向本站以外的任何地址发请求；发票只在浏览器内存里处理。测试里会证明这一点（见下文）。
- **断网可用**：页面加载完以后可以断网，照样能处理。
- 首次打开要加载约 14MB 的浏览器内 Python 运行时（Pyodide），之后浏览器会缓存。

自己在本地运行（开发者）：

```bash
python scripts/fetch_web_deps.py      # 下载 Pyodide 与 pypdf 到 web/vendor/（固定版本 + SHA-256 校验）
python -m http.server 8000            # 在仓库根目录运行
# 浏览器打开 http://localhost:8000/web/index.html
```

> 本地运行需要通过 http 打开（直接双击 html 文件，浏览器会禁止加载运行时）。普通用户直接用上面的在线链接即可。

## 命令行与 Python API

```bash
git clone https://github.com/labulaka-ai/fapiao-kit.git
cd fapiao-kit
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # 只依赖 pypdf
```

```bash
# 扫描：合并、去重、列出问题
.venv/bin/python -m fapiao_kit.cli scan 发票/
# 按本单位规则检查（规则文件示例见 rules/example.toml）
.venv/bin/python -m fapiao_kit.cli check 发票/ --rules rules/example.toml
# 改好名的副本放到新目录（原文件不动）
.venv/bin/python -m fapiao_kit.cli rename 发票/ -o 发票-改名/
# 导出 Excel 汇总表
.venv/bin/python -m fapiao_kit.cli export 发票/ -o 发票汇总.xlsx
# 机器可读输出
.venv/bin/python -m fapiao_kit.cli scan 发票/ --json
```

`pip install .` 后也可以直接用 `fapiao scan ...`。

```python
import fapiao_kit as fk
records = fk.scan("发票/", rules={"buyer_name": "示例大学", "buyer_tax_id": "99TEST000000000001"})
fk.export_xlsx(records, "发票汇总.xlsx")
fk.rename(records, "发票-改名/")
print(fk.to_json(records))
```

`demo/samples/` 里是 18 个合成样例文件（三件套、重复、被改过的 PDF、抬头错、税号错、旧版发票、损坏文件、扫描件……），可以直接拿来试：

```bash
.venv/bin/python -m fapiao_kit.cli check demo/samples --rules rules/example.toml
```

## 作为 agent skill 使用

仓库根目录的 `SKILL.md` 是给 AI agent（Claude Code、Codex、Cursor 等兼容 skill 的运行时）的入口：什么时候触发、按 `scan → check → 用户确认 → rename / export` 的顺序调用、JSON 字段含义，以及哪些事不许做（不改原文件、不上传发票内容、不一致时必须告诉用户、认不出的不猜、不做真伪查验）。

触发示例：

- 「帮我把这个文件夹里的发票整理成报销用的汇总表」
- 「这些发票有没有重复的？」
- 「检查一下抬头是不是都是 示例大学，税号对不对」
- 「把发票按 日期_销售方_金额 改名，放到新文件夹」

## 可信度：测试与验证

**测试体系**（本地全套 `pytest` 实际结果：**97 passed**，0 failed，0 skipped）：

- **合成样本，不用任何真实发票**：`tests/gen/samples.py` 自己生成 XML、OFD（三种写法：自定义标签 / 无标签逐字 DeltaX / CustomData + 多段 TextCode）和文字型 PDF（数电票版式和旧版增值税电子普通发票版式）。每个样本都带“测试样例 非真实发票”字样，公司名虚构，税号以 `99TEST` 开头，号码用 `99` 开头的号段，不画任何印章；有专门的测试检查这些约束；
- **字段级断言**：15 个样本文件 × 12 个字段，逐项与生成器的标准答案比对；另有随机往返测试：随机生成 30 张票 × 5 种文件（XML、3 种 OFD、PDF），解析结果必须与原字段完全一致；
- **合并与去重**：三件套合为一条且以 XML 为主；被改过的 PDF（价税合计不同）以 XML 为准并报出不一致；改名后的重复副本按哈希识别；**同日同额同销售方但号码不同的两张票不能被误合并**；无号码的文件只标“疑似重复”，不自动合并；
- **改名**：改名前后原目录所有文件的哈希和修改时间不变；副本与原文件逐字节相同；重名加序号；非空输出目录拒绝写入；
- **Excel 回读**：用 openpyxl 回读，校验合计 = 各行之和、大写金额正确、20 位发票号码以文本存储、类别小计、“需处理”清单；另用 LibreOffice 打开导出的 xlsx 并转成 CSV 核对合计（未安装 LibreOffice 时跳过）；
- **规则检查**：每条规则一个“检出”用例 + “不误报”用例（全角 / 半角括号、空格、税号大小写不算错）；
- **CLI**：每个命令的退出码和 JSON 结构；CLI 输出与 Python API 输出一致；
- **网页端到端（Playwright + Chromium）**：模拟把 18 个样例文件拖进页面 → 断言行数、标红条数、合计 → 点两个下载按钮，用 Python 回读下载的 xlsx 和 zip；
  - **零外发请求**：记录页面的全部网络请求，并拦截所有指向本机以外的请求，断言从拖入到下载结束 http(s) 请求数为 0、整个过程中没有任何外部请求；另有反向对照：页面主动 `fetch` 外部地址必须失败（被 CSP 拦下）；
  - **断网可用**：页面加载后切到离线模式，照样完成处理；
  - **一致性**：同一批样本，浏览器（Pyodide）输出的 JSON 与本机 Python 输出逐字段相同。

CI（GitHub Actions，`.github/workflows/test.yml`）下载网页依赖、安装 Chromium 和 LibreOffice 后运行全部测试。没有 `web/vendor/` 或 Chromium 时，5 个浏览器用例自动跳过，其余照常运行。

**线上页面实测**：对 GitHub Pages 上的线上页面跑同一套 Playwright 拖拽流程：18 个样例文件处理正常，下载的 Excel 合计正确；从拖入到下载结束，没有任何网络请求；浏览器结果与本机 Python 逐字段一致。

**还没有做的验证**（如实说明）：没有用真实发票做过抽检；样本的 XML 元素名、OFD 结构和 PDF 版式是按公开信息自行编写的，和各地、各开票软件实际输出的文件可能有差异。真实发票的抽检只会在本机进行，不入库、不上传；遇到识别不了的版式，欢迎提交**脱敏后**的诊断信息。

## 已知限制

- **只支持有文字层的文件**：扫描件、拍照、图片型 PDF 不做 OCR，只提示“需人工录入”；
- **票种**：数电专票 / 普票、旧版增值税电子发票（代码 + 号码）。铁路电子客票、航空行程单、通行费、财政票据还没有专门处理；
- **未经真实发票验证**：解析规则只在合成样本上测过（见上）；PDF 测试样本使用的是 reportlab 内置的 CID 字体，和真实发票嵌入的字体不同；
- **不做真伪查验**：查验要联网并输验证码，本工具坚持离线，请到国家税务总局全国增值税发票查验平台自行查验；
- **没有跨批次台账**：这次拖进去的文件之间能查重，但不会记住上个月已经报过的票（计划中）；
- **没有合并打印 PDF、报销单模板填写**（计划中）；网页版暂不支持直接拖入 zip 压缩包；
- 网页版首次加载约 14MB；只在 Chromium 上做了自动化测试，Firefox、Safari 和手机未测。

## 文件结构

```
fapiao-kit/
├── SKILL.md                 # agent 入口：触发场景、调用顺序、执行规则
├── README.md / README.en.md
├── LICENSE                  # Apache-2.0
├── requirements.txt         # 运行依赖：pypdf
├── requirements-dev.txt     # 测试依赖：pytest、reportlab、openpyxl、playwright
├── fapiao_kit/
│   ├── cli.py               # scan / check / rename / export
│   ├── api.py               # Python API；网页版也调用这里
│   ├── parsers.py           # XML / OFD / PDF 解析
│   ├── layout.py            # 按“文字 + 坐标”抽取字段（PDF 与无标签 OFD 共用）
│   ├── merge.py             # 跨格式合并、去重、一致性检查
│   ├── rules.py             # 抬头 / 税号等规则检查（TOML 规则文件）
│   ├── rename.py            # 改名复制（目录或 zip）
│   ├── export.py / xlsx.py  # Excel 汇总表（自带极简 xlsx 写入器，仅标准库）
│   └── money.py             # 金额与中文大写
├── site/index.html          # Pages 根路径跳转到 web/
├── web/                     # 网页版：index.html + app.js + style.css（vendor/ 不入库）
├── scripts/fetch_web_deps.py
├── rules/example.toml       # 规则文件示例（虚构数据）
├── demo/samples/            # 合成样例（测试样例 非真实发票）
├── tests/                   # pytest + Playwright；tests/gen/ 为样本生成器
└── .github/workflows/test.yml
```

## License

- 代码：Apache-2.0，见 `LICENSE`。
- 网页运行时 Pyodide（MPL-2.0）和 pypdf（BSD-3-Clause）不随仓库分发，由 `scripts/fetch_web_deps.py` 按固定版本下载，见 `NOTICE`。
- `demo/` 和 `tests/gen/` 生成的发票全部是合成测试数据，标有“测试样例 非真实发票”，不具备任何效力。本工具只读取发票，不提供开具或修改发票的功能。
- 本工具不替代税务查验，不对报销结果负责；报销要求以所在单位财务规定为准。

---

**作者**：Labulaka（[@labulaka-ai](https://github.com/labulaka-ai)），时空大数据方向博士在读
**公众号**：「时空AI深水区」——时空数据 × AI 的论文解读与一手实测
