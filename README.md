# 本地上市公司财务数据库

本项目用于为投资者建立一个本地化、免费优先、高准确度、可审计的上市公司财务数据库。它保存跟踪公司的结构化三大财务报表，并为 AI 分析和人工投研导出带来源、抓取时间、新鲜度和验证状态的数据。

## 为什么不直接用大模型读 PDF

直接让大模型从 PDF 年报或季报中读取财务数据，容易出现表格识别错误、单位误判、报告期误判、字段映射错误和遗漏。这个项目优先使用结构化数据源，并通过验证系统和人工复核流程控制数据质量。

## 功能概览

- 本地 SQLite 财务数据库。
- 支持利润表、资产负债表、现金流量表。
- US 数据优先使用 SEC EDGAR / XBRL / CompanyFacts。
- CN/HK 数据优先使用 AKShare。
- 数据验证系统：来源、新鲜度、完整性、一致性、时间序列和版本验证。
- 本地 Web 数据质量看板。
- CSV/JSONL 导出，方便 Excel、AI 和 RAG 工作流使用。
- 合规爬虫补充层，用于披露元数据和待复核候选，不污染可信财务事实表。

## 快速开始

```bash
python -m venv .venv
pip install -r requirements.txt
python main.py init-db --db financial_data.sqlite3
python main.py refresh --watchlist watchlist.example.csv --db financial_data.sqlite3
python main.py validate --db financial_data.sqlite3
python main.py serve --db financial_data.sqlite3 --host 127.0.0.1 --port 8000
```

浏览器访问：

```text
http://127.0.0.1:8000
```

## 示例 Watchlist

```csv
symbol,market,name,enabled,notes
AAPL,US,Apple Inc.,true,example
600519,CN,贵州茅台,true,example
00700,HK,Tencent Holdings,true,example
```

## 常用命令

```bash
python main.py init-db --db financial_data.sqlite3
python main.py refresh --watchlist watchlist.example.csv --db financial_data.sqlite3
python main.py validate --db financial_data.sqlite3
python main.py configure-crawler-source --db financial_data.sqlite3 --name cninfo --market CN --compliance-status allowed --enabled true --notes "public disclosure metadata only"
python main.py crawl-disclosures --watchlist watchlist.example.csv --db financial_data.sqlite3
python main.py export --db financial_data.sqlite3 --symbol AAPL --format csv,jsonl --out out/
python main.py serve --db financial_data.sqlite3 --host 127.0.0.1 --port 8000
```

## 当前实现状态

当前版本已具备第一版骨架：

- CLI 子命令已创建：`init-db`、`refresh`、`validate`、`configure-crawler-source`、`crawl-disclosures`、`review-candidates`、`export`、`serve`。
- `init-db` 会创建核心 SQLite 表、索引和默认验证规则，且可重复运行。
- `watchlist.example.csv` 可被读取，`enabled=false` 的行会跳过。
- `refresh` 已默认按市场接入真实结构化数据源：US 使用 SEC CompanyFacts，CN/HK 使用 AKShare，并会刷新 `data_freshness` 的最新结构化期间；内部仍支持注入 mock source，保证单元测试不依赖真实网络。
- 代码采集时会尽量从结构化数据源识别公司名称；当本地名称为空或仍等于股票代码时，会自动回填识别出的名称。
- `configure-crawler-source` 用于显式记录爬虫来源的合规状态和启用开关；`crawl-disclosures` 会读取 watchlist、同步公司，并在来源已启用且合规状态允许时通过 AKShare 的 CNINFO 公告接口采集 CN 披露元数据；默认不绕过合规开关。
- SEC adapter 已支持可注入 HTTP client 的 ticker-to-CIK 解析、CompanyFacts JSON 拉取和常见 XBRL 明细科目转换；解析 CompanyFacts 时会过滤同一 filing 内的比较期列和累计/季度候选，只为同一公司、期间、报表和科目保留当前报告期的最佳事实；单元测试使用 mock client，不依赖真实网络。
- AKShare adapter 已支持可注入 client 的 CN/HK 三大报表 DataFrame 转换、空 DataFrame 处理和接口异常包装；真实 AKShare 函数调用保留在薄封装中，并通过显式开启的 integration 测试验证。
- 单家公司刷新失败会写入 `quality_issues` 并继续处理其他公司；不支持市场会记录 `unsupported_market`。
- mock SEC/AKShare 结构化 payload 可保存到 `raw_payloads`，并标准化写入 `financial_facts`。
- 同一 payload hash 的同一财务事实重复写入会幂等更新，避免重复刷新或同一 payload 内候选行造成重复事实；payload hash 变化时才保留新版本。
- payload hash 会按原始结构化 payload 确定性生成；同一报告期在 payload hash 变化时会保留版本号。
- 报告期会规范化为 `YYYYQn` 或 `YYYYFY`，并派生 fiscal year / period；旧期间不会被当作最新结构化期间。
- 刷新流程会记录 `invalid_symbol` 和 `missing_field`，避免脏输入静默进入事实表。
- 新鲜度可记录 `current`、`stale`、`pending_structured_data`，滞后或缺失结构化数据会写入质量问题。
- `validate` 会写入 `validation_results` 和 `data_quality_scores`，并更新公司级数据状态。
- 验证后会同步更新事实行 `validation_status`，并按“取较低可信等级”更新 `quality_status`，避免验证问题仍被默认导出。
- 验证规则已覆盖来源字段、三大报表完整性、关键字段、资产负债表平衡、重复期间、极端跳变和 payload 修订检测。
- 爬虫补充层已支持公告文档 hash 去重、披露事件保存、禁用来源记录和未复核候选隔离；候选数值不会进入 `financial_facts`。
- `export` 支持 CSV/JSONL，默认只导出 `trusted` 和 `usable` 财务事实，并可按公司和财报期间筛选。
- Web app 工厂已可创建工作台、Companies、Company Detail、Validation Issues、Runs、Export 页面；一级导航仅保留工作台、公司、验证和导出。Runs 路由保留用于排查，但不作为第一版必要模块暴露。
- 工作台支持输入股票代码或已存在公司名称触发单家公司采集，默认只采集近 5 年财报，也可显式选择全部历史、最新季报或指定财报期间；工作台也支持输入股票代码和财报期间查询本地财务报表，并可手动触发验证。
- 工作台提供“运行爬虫”按钮，可按当前本地启用公司列表启动披露元数据爬虫；爬虫只保存公告元数据、文档 hash 和披露事件，不会把 PDF/HTML 数字写入可信财务事实表。
- Companies 页面是工作台公司列表的完整展开版，按同一表格结构展示全部公司，并在每家公司下方展开已采集期间、已采集报表和缺失报表；Company Detail 页面保留三大报表查看、财报期间切换和“验证本期报表”入口。
- Export 页面会调用同一套导出业务逻辑，支持选择公司和具体财报期间；点击导出会直接下载 CSV、JSONL 或包含两者的 ZIP，同时在数据库同目录的 `exports/` 下保留生成文件，默认仍只包含 `trusted` 和 `usable` 财务事实。

开发验证命令：

```bash
python -m pytest
```

默认测试不会访问真实外部数据源。真实 SEC / AKShare 集成测试需要显式开启：

```bash
RUN_INTEGRATION=1 python -m pytest
```

在 PowerShell 中：

```powershell
$env:RUN_INTEGRATION='1'
python -m pytest
```

在没有安装 pytest 的环境中，也可先用标准库测试入口验证：

```bash
python -m unittest discover -s tests -v
```

## 数据质量状态

- `trusted`：适合 AI 分析，无需默认人工复核。
- `usable`：可用，但存在轻微警告。
- `needs_review`：投资使用前需要人工复核。
- `stale`：结构化数据落后于最新已知披露。
- `failed`：验证失败或关键数据缺失。

AI 导出默认只包含 `trusted` 和 `usable` 数据。

状态来自验证规则、来源字段、新鲜度和采集结果的综合判断：无错误警告为 `trusted`；1 条警告为 `usable`；2 条及以上警告为 `needs_review`；结构化期间落后于最新披露期间为 `stale`；错误级验证结果、关键数据缺失、采集失败或不支持市场为 `failed`。验证同步事实行状态时只会按较低可信等级降级，不会把原本较低可信的数据自动升级。

## 开发方式

本项目采用轻量 TDD：

- 先理解需求和边界，再列核心验收标准。
- 只为核心业务逻辑写最少数量的测试。
- 不为 UI、样式、简单 CRUD 写测试。
- 单元测试使用 mock 数据。
- 真实数据源测试标记为 integration。
- 优先写小函数，修改尽量小步推进。
- 输出只说明关键改动、测试结果和下一步建议。

## 项目文档

- `AGENTS.md`：项目协作准则。
- `REQUIREMENTS.md`：需求分析文档。
- `TASKS.md`：TDD 任务清单。
- `TECHNICAL_DESIGN.md`：技术方案。

## 免责声明

本项目不提供投资建议，不进行自动交易。数据仅供研究使用，关键投资结论应自行核验。
