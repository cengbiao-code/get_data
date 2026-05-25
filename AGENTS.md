# AGENTS.md

## Project Goal

本项目为投资者建立一个本地上市公司财务数据库，用于 AI 分析和人工投研。系统应免费优先、高准确度、可审计，并能长期跟踪关注公司的结构化财务数据。

第一版重点覆盖三大财务报表：

- 利润表。
- 资产负债表。
- 现金流量表。

## Accuracy Principles

- 不把 PDF 自动抽取结果直接写入可信事实表。
- 不把旧结构化数据静默当成最新数据。
- 所有财务事实必须保留来源、抓取时间、payload hash 和可信状态。
- 缺失值必须显式记录，不允许默认填零。
- 异常值应进入验证结果或人工复核流程，不应被静默删除或自动修正。
- AI 导出默认只包含 `trusted` 和 `usable` 数据。

## Technical Boundaries

- SQLite 是本项目的可信主数据库。
- CSV 和 JSONL 是导出格式，不是主存储。
- CLI 和本地 Web UI 必须共用同一套业务逻辑。
- 数据采集、标准化、存储、验证、导出、Web 查询应保持模块边界清晰。
- Web UI 默认只绑定 `127.0.0.1`，第一版不做多用户部署。

## Data Source Strategy

- US 公司优先使用 SEC EDGAR / XBRL / CompanyFacts。
- CN 和 HK 公司优先使用 AKShare 结构化财务报表接口。
- AKShare 未更新时，必须标记为 `stale` 或 `pending_structured_data`。
- 不支持的市场必须明确记录为 `unsupported_market`。
- 爬虫只补充披露元数据、公告文件链接、文件 hash 和待复核候选。
- 未复核的 PDF/HTML 解析数字不得进入 `financial_facts`。

## Validation System

验证系统是核心模块，不是可选功能。刷新数据后应自动运行验证，也应支持手动运行。

验证范围包括：

- 来源验证：检查 source、source URL、payload hash、fetched_at、confidence。
- 新鲜度验证：检查最新结构化期间是否落后于最新披露期间。
- 完整性验证：检查三大报表和关键字段是否存在。
- 一致性验证：检查资产负债表、利润表、现金流量表的基本财务关系。
- 时间序列验证：检查重复期间、缺失期间和异常跳变。
- 版本验证：检查同一报告期 payload hash 变化并保留历史版本。

数据质量状态包括：

- `trusted`
- `usable`
- `needs_review`
- `stale`
- `failed`

## Lightweight TDD Requirements

- 先理解需求和边界，不要立刻写代码。
- 实现前先列出核心验收标准。
- 只为核心业务逻辑写最少数量的测试。
- 不为 UI、样式、简单 CRUD 写测试。
- 单元测试使用 mock 数据，不依赖真实网络。
- 真实数据源测试必须标记为 integration。
- 优先写小函数，便于后续测试和复用。
- 每次修改尽量小步推进。
- 命令、schema、接口或质量策略变化时，必须同步更新文档。
- 输出时只说明关键改动、测试结果和下一步建议，避免大段解释。

## Do Not Build

- 不提供自动投资建议。
- 不做自动交易。
- 不绕过登录、验证码、付费墙、反爬限制或访问控制。
- 不把未复核 PDF 数字写入可信表。
- 不用低可信度来源静默覆盖 SEC 或 AKShare 的结构化数据。
