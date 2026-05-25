# 本地上市公司财务数据库任务清单

## 0. 项目约定

- 主数据库：SQLite。
- 主语言：Python 3.11+。
- 开发方式：轻量 TDD。
- 运行方式：CLI + 本地 Web UI。
- 第一版数据范围：三大财务报表。
- 第一版市场范围：`US`、`CN`、`HK`。
- 第一版不做 PDF 自动抽表进入可信事实表。
- 所有接口、命令、schema 变化必须同步文档。
- 开发前先理解需求并列出核心验收标准。
- 只为核心业务逻辑写最少数量的测试；不为 UI、样式、简单 CRUD 写测试。
- 优先写小函数，每次修改尽量小步推进。
- 输出只说明关键改动、测试结果和下一步建议。

## 1. 项目初始化

- [x] 先写测试：`python main.py --help` 可运行。
- [x] 先写测试：核心模块可以被导入。
- [x] 先写测试：`watchlist.example.csv` 字段完整。
- [x] 创建基础项目结构。
  - `main.py`
  - `db/`
  - `models.py`
  - `normalizer.py`
  - `validator.py`
  - `exporter.py`
  - `sources/`
  - `crawler/`
  - `web/`
  - `tests/`
- [x] 创建依赖配置文件。
  - `requirements.txt` 或 `pyproject.toml`
- [x] 创建示例跟踪清单。
  - `watchlist.example.csv`
- [x] 确认 CLI 入口支持 `init-db`、`refresh`、`validate`、`crawl-disclosures`、`review-candidates`、`export`、`serve`。
- [x] 将 `crawl-disclosures` CLI 接到爬虫补充层业务逻辑。

## 2. 数据库设计与初始化

- [x] 先写测试：初始化数据库后所有核心表存在。
- [x] 先写测试：重复执行 `init-db` 不破坏已有数据。
- [x] 先写测试：默认验证规则能写入 `validation_rules`。
- [x] 先写测试：关键索引存在。
- [x] 创建 `companies` 表。
- [x] 创建 `fetch_runs` 表。
- [x] 创建 `financial_facts` 表。
- [x] 创建 `raw_payloads` 表。
- [x] 创建 `quality_issues` 表。
- [x] 创建 `disclosure_events` 表。
- [x] 创建 `data_freshness` 表。
- [x] 创建 `validation_rules` 表。
- [x] 创建 `validation_results` 表。
- [x] 创建 `data_quality_scores` 表。
- [x] 创建 `manual_reviews` 表。
- [x] 创建 `crawler_sources` 表。
- [x] 创建 `crawler_runs` 表。
- [x] 创建 `crawler_documents` 表。
- [x] 创建 `extracted_candidates` 表。
- [x] 添加必要索引。
- [x] 实现 `python main.py init-db --db financial_data.sqlite3`。

## 3. Watchlist 管理

- [x] 先写测试：能读取合法 `watchlist.csv`。
- [x] 先写测试：能跳过 `enabled=false`。
- [x] 先写测试：缺少必填字段时报错。
- [x] 先写测试：不支持市场写入 `quality_issues`。
- [x] 定义字段：`symbol`、`market`、`name`、`enabled`、`notes`。
- [x] 实现 watchlist 读取。
- [x] 将 watchlist 公司同步到 `companies` 表。
- [x] 编写 watchlist 示例文件。

## 4. 数据源 Mock 与适配器

### 4.1 SEC 数据源

- [x] 先用 mock SEC payload 测试保存到 `raw_payloads`。
- [x] 先用 mock SEC payload 测试标准化输入协议。
- [x] 实现 SEC 公司代码到 CIK 的解析方案。
- [x] 实现 SEC CompanyFacts 拉取。
- [x] 扩展 SEC 常见 XBRL 明细科目映射。
- [x] 保存 SEC 原始 JSON。
- [x] 设置 SEC 数据来源置信度为 `official`。
- [x] 处理 SEC 接口失败。
- [x] 处理 SEC 代码无效、字段缺失。

### 4.2 AKShare 数据源

- [x] 先用 mock AKShare dataframe 测试保存到 `raw_payloads`。
- [x] 先写测试：空 payload 记录 `empty_payload`。
- [x] 接入 AKShare 适配器薄封装。
- [x] 实现 A股三大报表拉取接口。
- [x] 实现港股三大报表拉取接口。
- [x] 将真实 SEC/AKShare 数据源接入 CLI `refresh` 默认路径。
- [x] 设置 AKShare 数据来源置信度为 `structured_open_source`。
- [x] 处理 AKShare 缺失、接口变化。
- [x] 处理 AKShare 空数据、代码无效。

## 5. 财务数据标准化

- [x] 先写测试：SEC mock 数据能转成 `financial_facts`。
- [x] 先写测试：AKShare mock 数据能转成 `financial_facts`。
- [x] 先写测试：三大报表类型统一为 `income_statement`、`balance_sheet`、`cash_flow`。
- [x] 先写测试：缺失值不填零。
- [x] 先写测试：同一报告期重复刷新保留版本。
- [x] 定义统一财务事实字段。
- [x] 统一报告期格式。
- [x] 统一金额数值类型。
- [x] 保留原始字段名。
- [x] 写入 `financial_facts`。
- [x] 用 payload hash 判断来源数据是否变化。

## 6. 数据新鲜度管理

- [x] 先写测试：最新结构化期间等于最新披露期间时为 `current`。
- [x] 先写测试：AKShare 缺少最新披露期时为 `pending_structured_data`。
- [x] 先写测试：旧数据不被标记为最新。
- [x] 设计 freshness 状态：`current`、`stale`、`pending_structured_data`、`unknown`、`unsupported_market`、`error`。
- [x] 记录最新结构化报告期。
- [x] 记录最新已知披露报告期。
- [x] 记录最新披露日期。
- [x] 记录最新刷新时间。
- [x] 将滞后和缺失问题写入 `quality_issues`。

## 7. 验证系统

### 7.1 验证框架

- [x] 先写测试：`validate` 命令可执行。
- [x] 先写测试：验证结果写入 `validation_results`。
- [x] 先写测试：质量评分写入 `data_quality_scores`。
- [x] 初始化默认验证规则到 `validation_rules`。
- [x] 支持刷新后自动运行验证。
- [x] 支持手动单独运行验证。

### 7.2 验证规则

- [x] 来源验证：缺少 source 触发问题。
- [x] 来源验证：缺少 fetched_at 触发问题。
- [x] 来源验证：缺少 payload hash 触发问题。
- [x] 新鲜度验证：滞后数据标记 `stale`。
- [x] 完整性验证：三大报表缺失触发 `needs_review`。
- [x] 完整性验证：关键字段缺失触发 `needs_review` 或 `failed`。
- [x] 一致性验证：资产不等于负债加权益触发问题。
- [x] 时间序列验证：重复报告期触发问题。
- [x] 时间序列验证：极端跳变标记 `needs_review`。
- [x] 版本验证：payload hash 变化记录来源修订。

## 8. 数据导出

- [x] 先写测试：CSV 导出包含财务事实字段。
- [x] 先写测试：JSONL 导出每行是完整记录。
- [x] 先写测试：默认只导出 `trusted` 和 `usable`。
- [x] 先写测试：`stale` 和 `needs_review` 默认排除。
- [x] 实现 CSV 导出。
- [x] 实现 JSONL 导出。
- [x] 导出字段包含来源信息、freshness 状态、validation 状态、数据质量评分。
- [x] 提供参数允许导出 `needs_review` 或 `stale` 数据。

## 9. Web 可视化界面

- [x] 先写测试：`serve` 命令可创建 FastAPI app。
- [x] 先写测试：Dashboard 页面返回 200。
- [x] 先写测试：Companies 页面返回 200。
- [x] 先写测试：Web 输入股票代码可查询公司财务报表。
- [x] 先写测试：Web 查询可按财报期间过滤。
- [x] 先写测试：Web 输入股票代码或已存在公司名称可触发单家公司采集。
- [x] 先写测试：Web 采集可选择指定期间或最新季报。
- [x] 先写测试：公司列表展示已采集期间和缺失报表。
- [x] 先写测试：Dashboard 公司数量可展开公司名单并链接到详情页。
- [x] 先写测试：Validation Issues 页面返回 200。
- [x] 先写测试：Dashboard 能显示 `trusted`、`usable`、`needs_review`、`stale`、`failed` 统计。
- [x] 实现本地 Web 服务。
- [x] 实现 Dashboard 数据质量看板。
- [x] 实现股票代码查询入口。
- [x] 实现财报期间查询过滤。
- [x] 实现 Web 单家公司采集入口。
- [x] 实现采集范围选择：全部历史、最新季报、指定期间。
- [x] 将默认采集范围设为近 5 年，避免默认全历史撑大本地数据库。
- [x] 实现 Companies 公司列表页。
- [x] 实现公司已采集期间和缺失报表展示。
- [x] 收敛 Dashboard 公司列表入口，去掉重复展开名单。
- [x] 实现 Company Detail 公司详情页。
- [x] 实现 Validation Issues 问题页。
- [x] 保留 Runs 刷新历史页作为内部排查路由，不放入一级导航。
- [x] 实现 Export 导出页。
- [x] 实现手动触发刷新。
- [x] 实现手动触发验证。
- [x] 确认 Web UI 与 CLI 使用同一个 SQLite 数据库和同一业务逻辑。

## 10. 爬虫补充层

- [x] 先写测试：爬虫来源禁用时记录 `crawler_disabled`。
- [x] 先写测试：重复公告按 hash 去重。
- [x] 先写测试：爬虫只写入 `crawler_documents` 和 `disclosure_events`。
- [x] 先写测试：未复核候选数据只进入 `extracted_candidates`。
- [x] 先写测试：未复核候选数据不会进入 `financial_facts`。
- [x] 实现爬虫基类。
- [x] 实现 robots/条款检查记录。
- [x] 实现限速、缓存、重试上限。
- [x] 实现 CN 披露元数据最小采集适配。
- [x] 保存公告文件链接和 hash。
- [x] 检测 AKShare 滞后但公告已披露的情况。
- [x] 禁止未复核候选数据进入可信财务事实表。

## 11. 错误处理与日志

- [x] 设计统一错误类型。
- [x] 数据源失败时记录错误并继续处理其他公司。
- [x] 代码无效时记录 `invalid_symbol`。
- [x] 市场不支持时记录 `unsupported_market`。
- [x] 数据为空时记录 `empty_payload`。
- [x] 字段缺失时记录 `missing_field`。
- [x] 网络或接口异常写入 `quality_issues`。
- [x] 每次运行写入 `fetch_runs` 或 `crawler_runs`。

## 12. 文档任务

- [x] 创建或更新 `AGENTS.md`。
- [x] 创建或更新 `REQUIREMENTS.md`。
- [x] 创建或更新 `TASKS.md`。
- [x] 创建或更新 `TECHNICAL_DESIGN.md`。
- [x] 创建或更新 `README.md`。
- [x] 命令、接口、schema、质量策略变化时同步文档。
- [x] 真实数据源测试标记为 `integration`，默认跳过，显式开启后运行。

## 13. 第一版验收清单

- [x] 所有已实现核心路径有测试覆盖，且测试通过。
- [x] 可以初始化 SQLite 数据库。
- [x] 可以读取 watchlist。
- [x] 可以用 mock 数据源刷新至少一个 US 公司。
- [x] 可以用 mock 数据源刷新至少一个 CN 或 HK 公司。
- [x] CLI `refresh` 默认使用 SEC/AKShare 真实结构化数据源。
- [x] 可以保存原始 payload。
- [x] 可以写入标准化三大报表事实。
- [x] 可以保留历史版本。
- [x] 可以标记 AKShare 缺失或滞后。
- [x] 可以运行验证系统。
- [x] 可以生成数据质量评分。
- [x] Web UI 可以显示数据质量看板。
- [x] 可以导出 CSV。
- [x] 可以导出 JSONL。
- [x] 导出数据包含来源、抓取时间、新鲜度、验证状态。
- [x] 爬虫补充层可用但不污染可信数据。
- [x] 出错时批处理不中断。
