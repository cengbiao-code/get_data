# 本地上市公司财务数据库技术方案

## 1. 技术栈

- 语言：Python 3.11+
- 数据库：SQLite
- 测试：pytest
- Web 后端：FastAPI
- Web 模板：Jinja2
- 前端样式：原生 CSS，第一版不引入复杂前端构建链
- 数据处理：pandas
- HTTP 请求：requests 或 httpx
- 数据源：SEC EDGAR / XBRL / CompanyFacts、AKShare、合规爬虫补充层

## 2. 项目结构

```text
get_data/
  main.py
  db/
    __init__.py
    connection.py
    schema.py
    companies.py
    facts.py
    runs.py
    quality.py
  models.py
  normalizer.py
  validator.py
  exporter.py
  config.py
  sources/
    __init__.py
    sec.py
    akshare_source.py
    disclosure_check.py
  crawler/
    __init__.py
    base.py
    cninfo.py
    sse.py
    szse.py
    document_store.py
  web/
    __init__.py
    app.py
    routes.py
    templates/
      dashboard.html
      companies.html
      company_detail.html
      validation_issues.html
      runs.html
      export.html
    static/
      styles.css
  tests/
    test_db.py
    test_watchlist.py
    test_normalizer.py
    test_validator.py
    test_exporter.py
    test_web.py
    test_crawler.py
  watchlist.example.csv
  AGENTS.md
  REQUIREMENTS.md
  TASKS.md
  TECHNICAL_DESIGN.md
  README.md
```

## 3. 架构分层

系统分为五层：

- 数据采集层：SEC 适配器、AKShare 适配器、披露状态检查、爬虫补充采集。
- 标准化层：将不同来源数据统一为长表财务事实。
- 存储层：SQLite 保存公司、原始 payload、财务事实、刷新记录、验证结果、爬虫文档。
- 验证层：执行来源、新鲜度、完整性、一致性、时间序列、版本验证。
- 交互层：CLI 命令和本地 Web UI。

CLI 和 Web UI 必须共用同一套业务模块，不能各自实现刷新、验证或导出逻辑。

## 4. 数据库设计

主要表：

- `companies`：公司代码、市场、名称、币种、启用状态、数据状态。
- `fetch_runs`：刷新任务的开始时间、结束时间、状态、成功数、失败数。
- `financial_facts`：标准化财务事实长表。
- `raw_payloads`：原始 API 响应、payload hash 和来源信息。
- `quality_issues`：缺失、滞后、接口失败、不支持市场等问题。
- `disclosure_events`：已知公告或报告披露事件。
- `data_freshness`：最新结构化期间、最新披露期间、是否滞后。
- `validation_rules`：验证规则配置。
- `validation_results`：每次验证结果。
- `data_quality_scores`：公司级、报表级、期间级质量评分。
- `manual_reviews`：人工复核记录。
- `crawler_sources`：爬虫来源和合规状态。
- `crawler_runs`：爬虫任务记录。
- `crawler_documents`：公告和文件元数据。
- `extracted_candidates`：PDF/HTML 解析候选值，默认 `unverified`。

## 5. 关键数据流

### 5.1 初始化

`init-db` 流程：

1. 打开或创建 SQLite 数据库。
2. 创建所有表和索引。
3. 初始化默认验证规则。
4. 可重复执行，不破坏已有数据。

### 5.2 刷新

`refresh` 流程：

1. 读取 `watchlist.csv`。
2. 同步到 `companies`。
3. 创建 `fetch_runs`。
4. 按市场选择默认结构化数据源：US 使用 SEC CompanyFacts，CN/HK 使用 AKShare；测试和内部调用可注入 mock source。
5. 抓取结构化财务数据。
6. 保存 `raw_payloads`。
7. 标准化为 `financial_facts`。
8. 根据已保存事实刷新 `data_freshness` 的最新结构化期间；若已有披露事件，则同时比较最新披露期。
9. 写入 `quality_issues`。
10. 自动运行验证。
11. 更新 `fetch_runs` 结果。

### 5.3 验证

`validate` 流程：

1. 加载启用的验证规则。
2. 查询最新财务事实。
3. 执行来源、新鲜度、完整性、一致性、时间序列、版本验证。
4. 写入 `validation_results`。
5. 生成 `data_quality_scores`。
6. 不修改原始财务事实。

### 5.4 爬虫补充

`crawl-disclosures` 流程：

1. 读取 watchlist。
2. 检查 crawler source 是否允许使用。
3. 低频采集披露元数据。
4. 保存公告标题、日期、类型、链接和 hash。
5. 更新 `disclosure_events`。
6. 若发现披露已更新但结构化数据未更新，刷新 `data_freshness`，标记 `stale` 或 `pending_structured_data` 并记录 `pending_structured_data` 质量问题。
7. 不写入可信财务事实表。

### 5.5 导出

`export` 流程：

1. 查询指定公司或范围。
2. 默认过滤 `trusted` 和 `usable`。
3. 附带来源、新鲜度、验证状态、质量评分。
4. 输出 CSV 和 JSONL。

### 5.6 Web 查询

Web UI 通过应用服务读取同一个 SQLite 数据库。第一版一级导航只暴露工作台、公司、验证和导出四个必要模块；Runs 路由保留用于排查刷新或爬虫历史，但不在导航中展示。工作台提供股票代码和财报期间查询入口，查询命中后展示该公司的本地财务事实表；查询本身不触发外部数据刷新。工作台还提供单家公司采集入口，输入股票代码可按市场触发结构化数据刷新，默认采集近 5 年财报，并支持显式选择全部历史、最新季报和指定期间；输入公司名称时仅匹配本地已存在公司，避免名称歧义导致采集错误。Companies 页面展示每家公司已采集期间、已采集报表和缺失报表。Company Detail 页面展示三大报表，并提供轻量财报期间切换入口。

## 6. CLI 接口

```bash
python main.py init-db --db financial_data.sqlite3
python main.py refresh --watchlist watchlist.csv --db financial_data.sqlite3
python main.py validate --db financial_data.sqlite3
python main.py crawl-disclosures --watchlist watchlist.csv --db financial_data.sqlite3
python main.py review-candidates --db financial_data.sqlite3
python main.py export --db financial_data.sqlite3 --symbol AAPL --format csv,jsonl --out out/
python main.py serve --db financial_data.sqlite3 --host 127.0.0.1 --port 8000
```

## 7. Web UI 设计

本地 Web UI 默认绑定 `127.0.0.1`。

必要模块：

- 工作台：查询财务报表、单家公司采集、数据质量总览、手动验证入口。
- Companies：公司列表、已采集期间、已采集报表和缺失报表。
- Company Detail：三大报表、原始来源、payload hash、质量状态和财报期间切换。
- Validation Issues：最近验证问题和手动验证入口。
- Export：选择公司并导出默认可信范围的数据。

内部排查页面：

- Runs：刷新任务和爬虫任务历史，保留路由但不在一级导航中展示。

第一版 UI 应偏向投研工具：信息密度适中、状态清晰、避免装饰性页面。

## 8. 验证规则

第一版内置规则：

- `source_required`
- `fetched_at_required`
- `payload_hash_required`
- `freshness_current_or_marked`
- `three_statements_present`
- `key_income_fields_present`
- `key_balance_fields_present`
- `key_cash_flow_fields_present`
- `balance_sheet_balances`
- `duplicate_period_detected`
- `large_change_detected`
- `payload_revision_detected`

质量状态：

- `trusted`
- `usable`
- `needs_review`
- `stale`
- `failed`

## 9. 爬虫约束

- 爬虫只用于补充披露元数据和原始文件信息。
- CN 披露元数据最小适配通过注入客户端采集公告列表和文件内容，保存标题、链接、报告期、披露日、类型和文件 hash。
- 不绕过登录、验证码、反爬、付费墙或访问控制。
- 必须记录 robots/条款检查结果。
- 必须限速、缓存、设置重试上限。
- HKEXnews 默认禁用直接爬取，除非确认合规访问方式。
- 未复核解析候选不得导出给 AI。

## 10. 测试策略

项目采用轻量 TDD 流程：先理解需求和边界，先列核心验收标准，再决定是否需要测试。测试只覆盖核心业务逻辑，数量保持最少；UI、样式和简单 CRUD 不写专门测试。实现时优先拆小函数，方便后续对关键逻辑补测。

单元测试：

- 数据库初始化。
- watchlist 解析。
- 标准化。
- 验证规则。
- 导出。
- Web 查询和采集的核心业务路径。

集成测试：

- US/CN/HK 刷新流程。
- AKShare 缺失或滞后。
- 爬虫补充披露流程。
- Web 服务核心路由可用性。

数据质量测试：

- 缺失字段。
- 重复报告期。
- 资产负债表不平衡。
- 极端同比变化。
- payload hash 变化。

验收测试：

- 初始化数据库成功。
- CLI 可刷新和验证。
- Web UI 可显示数据质量看板。
- CSV/JSONL 导出包含来源、新鲜度、验证状态和质量评分。
- 未验证候选数据不会进入可信导出。
