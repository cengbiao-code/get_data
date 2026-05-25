from __future__ import annotations

from html import escape
from pathlib import Path
import re
from urllib.parse import parse_qs, quote, urlsplit

from models import WatchlistCompany
import refresher
import validator
from web import queries


try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, Response
except ModuleNotFoundError:
    FastAPI = None
    HTMLResponse = None
    Response = None


get_dashboard_stats = queries.get_dashboard_stats


class SimpleResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


CSS_PATH = Path(__file__).with_name("app.css")


STATEMENT_LABELS = {
    "income_statement": "利润表",
    "balance_sheet": "资产负债表",
    "cash_flow": "现金流量表",
}
LINE_ITEM_LABELS = {
    "revenue": "营业收入",
    "cost_of_revenue": "营业成本",
    "gross_profit": "毛利润",
    "operating_income": "营业利润",
    "operating_expenses": "营业费用",
    "research_and_development": "研发费用",
    "selling_general_and_administrative": "销售、一般及管理费用",
    "general_and_administrative": "一般及管理费用",
    "selling_and_marketing": "销售和市场费用",
    "interest_expense": "利息费用",
    "net_interest_income_expense": "利息收支净额",
    "pretax_income": "税前利润",
    "income_tax_expense": "所得税费用",
    "net_income": "净利润",
    "earnings_per_share_basic": "基本每股收益",
    "earnings_per_share_diluted": "摊薄每股收益",
    "weighted_average_shares_basic": "基本加权平均股数",
    "weighted_average_shares_diluted": "摊薄加权平均股数",
    "total_assets": "资产总计",
    "current_assets": "流动资产",
    "cash_and_cash_equivalents": "现金及现金等价物",
    "cash_cash_equivalents_and_restricted_cash": "现金、现金等价物及受限现金",
    "short_term_investments": "短期投资",
    "marketable_securities": "有价证券",
    "accounts_receivable": "应收账款",
    "inventory": "存货",
    "prepaid_expenses_and_other_current_assets": "预付费用及其他流动资产",
    "property_plant_and_equipment_net": "固定资产净额",
    "goodwill": "商誉",
    "intangible_assets_net": "无形资产净额",
    "other_current_assets": "其他流动资产",
    "other_noncurrent_assets": "其他非流动资产",
    "total_liabilities": "负债合计",
    "current_liabilities": "流动负债",
    "accounts_payable": "应付账款",
    "accrued_liabilities": "应计负债",
    "current_contract_liabilities": "流动合同负债",
    "current_long_term_debt": "一年内到期长期债务",
    "long_term_debt": "长期债务",
    "current_operating_lease_liability": "流动经营租赁负债",
    "noncurrent_operating_lease_liability": "非流动经营租赁负债",
    "deferred_revenue_current": "流动递延收入",
    "deferred_revenue_noncurrent": "非流动递延收入",
    "deferred_tax_liabilities_noncurrent": "非流动递延所得税负债",
    "total_equity": "所有者权益合计",
    "retained_earnings": "留存收益",
    "accumulated_other_comprehensive_income_loss": "累计其他综合收益/损失",
    "operating_cash_flow": "经营活动现金流量净额",
    "investing_cash_flow": "投资活动现金流量净额",
    "financing_cash_flow": "筹资活动现金流量净额",
    "capital_expenditure": "资本开支",
    "business_acquisitions_net": "收购业务支付现金净额",
    "purchases_of_investments": "购买投资支付现金",
    "proceeds_from_investments": "出售和到期投资收到现金",
    "dividends_paid": "支付股利",
    "share_repurchases": "股票回购",
    "proceeds_from_common_stock_issuance": "发行普通股收到现金",
    "proceeds_from_long_term_debt": "发行长期债务收到现金",
    "repayments_of_long_term_debt": "偿还长期债务",
    "depreciation_depletion_and_amortization": "折旧、损耗及摊销",
    "share_based_compensation": "股权激励费用",
    "change_in_accounts_receivable": "应收账款变动",
    "change_in_inventory": "存货变动",
    "change_in_accounts_payable": "应付账款变动",
    "net_change_in_cash_and_cash_equivalents": "现金及现金等价物净变动",
}
QUALITY_LABELS = {
    "trusted": "可信",
    "usable": "可用",
    "needs_review": "需复核",
    "stale": "已滞后",
    "failed": "失败",
}
RUN_STATUS_LABELS = {
    "completed": "完成",
    "partial_failed": "部分失败",
    "failed": "失败",
    "running": "运行中",
}


def _label(mapping: dict[str, str], value: str | None) -> str:
    if value is None:
        return ""
    return mapping.get(value, value)


def read_static_css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def render_page(title: str, body: str, *, subtitle: str = "") -> str:
    subtitle_html = (
        f"<span class=\"brand-subtitle\">{escape(subtitle)}</span>"
        if subtitle
        else "<span class=\"brand-subtitle\">SQLite 可信主库 · 结构化财报 · 本地优先</span>"
    )
    return f"""
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{escape(title)}</title>
        <link rel="stylesheet" href="/static/app.css">
      </head>
      <body>
        <div class="app-shell">
          <header class="app-header">
            <div class="app-header-inner">
              <a class="brand" href="/">
                <span class="brand-title">本地财务数据库</span>
                {subtitle_html}
              </a>
              <nav class="app-nav" aria-label="主导航">
                <a href="/">工作台</a>
                <a href="/companies">公司</a>
                <a href="/validation-issues">验证</a>
                <a href="/export">导出</a>
              </nav>
            </div>
          </header>
          <main class="page">
            {body}
          </main>
        </div>
      </body>
    </html>
    """


def render_status_badge(status: str | None) -> str:
    safe_status = escape(status or "unknown")
    return (
        f"<span class=\"status-badge {safe_status}\">"
        f"{escape(_label(QUALITY_LABELS, status))}</span>"
    )


def render_options(options: list[tuple[str, str]], selected: str) -> str:
    return "".join(
        f"<option value=\"{escape(value)}\"{' selected' if value == selected else ''}>"
        f"{escape(label)}</option>"
        for value, label in options
    )


def render_text_field(
    *,
    field_id: str,
    name: str,
    label: str,
    value: str = "",
    placeholder: str = "",
    wide: bool = False,
) -> str:
    field_class = "field field-wide" if wide else "field"
    return (
        f"<div class=\"{field_class}\"><label for=\"{escape(field_id)}\">{escape(label)}</label>"
        f"<input id=\"{escape(field_id)}\" name=\"{escape(name)}\" value=\"{escape(value)}\" "
        f"placeholder=\"{escape(placeholder)}\" /></div>"
    )


def render_select_field(
    *,
    field_id: str,
    name: str,
    label: str,
    options: list[tuple[str, str]],
    selected: str,
) -> str:
    return (
        f"<div class=\"field\"><label for=\"{escape(field_id)}\">{escape(label)}</label>"
        f"<select id=\"{escape(field_id)}\" name=\"{escape(name)}\">"
        f"{render_options(options, selected)}</select></div>"
    )


def render_submit_field(label: str) -> str:
    return (
        "<div class=\"field field-wide\">"
        f"<button type=\"submit\">{escape(label)}</button>"
        "</div>"
    )


def render_stock_search_form(symbol: str = "", report_period: str = "") -> str:
    return (
        "<form class=\"form-card panel\" method=\"get\" action=\"/search\">"
        "<h2>查询财务报表</h2>"
        "<div class=\"form-grid\">"
        f"{render_text_field(field_id='stock-symbol', name='symbol', label='股票代码', value=symbol, placeholder='AAPL / 600519 / 00700')}"
        f"{render_text_field(field_id='search-period', name='report_period', label='财报期间', value=report_period, placeholder='例如 2025Q4，可留空查全部')}"
        f"{render_submit_field('查询财务报表')}"
        "</div>"
        "</form>"
    )


def render_collect_form(
    query: str = "",
    market: str = "auto",
    name: str = "",
    history_scope: str = "recent_5y",
    report_period: str = "",
) -> str:
    markets = [
        ("auto", "自动识别"),
        ("US", "US 美股"),
        ("CN", "CN A股"),
        ("HK", "HK 港股"),
    ]
    scope_options = [
        ("recent_5y", "近5年财报"),
        ("all", "全部历史财报"),
        ("latest_quarter", "最新季报"),
        ("period", "指定期间"),
    ]
    return (
        "<form class=\"form-card panel\" method=\"get\" action=\"/collect\">"
        "<h2>采集公司数据</h2>"
        "<div class=\"form-grid\">"
        f"{render_text_field(field_id='collect-query', name='query', label='公司名称或股票代码', value=query, placeholder='AAPL / 600519 / Apple Inc.')}"
        f"{render_select_field(field_id='collect-market', name='market', label='市场', options=markets, selected=market)}"
        f"{render_text_field(field_id='collect-name', name='name', label='公司名称', value=name, placeholder='可选，代码采集时用于保存名称')}"
        f"{render_select_field(field_id='history-scope', name='history_scope', label='采集范围', options=scope_options, selected=history_scope)}"
        f"{render_text_field(field_id='collect-period', name='report_period', label='财报期间', value=report_period, placeholder='指定期间时填写，如 2025Q4', wide=True)}"
        f"{render_submit_field('开始采集')}"
        "</div>"
        "</form>"
    )


def render_command_center(
    symbol: str = "",
    report_period: str = "",
    collect_query: str = "",
    market: str = "auto",
    name: str = "",
    history_scope: str = "recent_5y",
    collect_period: str = "",
) -> str:
    return (
        "<section class=\"top-query-collect\">"
        f"{render_stock_search_form(symbol, report_period)}"
        f"{render_collect_form(collect_query, market, name, history_scope, collect_period)}"
        "</section>"
    )


def render_period_filter_form(symbol: str, report_period: str = "") -> str:
    return (
        "<form class=\"inline-filter\" method=\"get\" action=\"/search\">"
        f"<input type=\"hidden\" name=\"symbol\" value=\"{escape(symbol)}\" />"
        f"{render_text_field(field_id='period-filter', name='report_period', label='切换财报期间', value=report_period, placeholder='例如 2025Q4')}"
        "<button type=\"submit\">查看</button>"
        "</form>"
    )


def render_quality_summary(quality: dict[str, int]) -> str:
    return (
        "<section class=\"quality-summary\" aria-label=\"数据质量状态\">"
        f"<span class=\"chip\">可信：{quality['trusted']}</span>"
        f"<span class=\"chip\">可用：{quality['usable']}</span>"
        f"<span class=\"chip\">需复核：{quality['needs_review']}</span>"
        f"<span class=\"chip\">已滞后：{quality['stale']}</span>"
        f"<span class=\"chip\">失败：{quality['failed']}</span>"
        "</section>"
    )


def render_company_list_panel(db_path: str | Path, company_count: int) -> str:
    rows = queries.get_company_list_summary_rows(db_path)
    if rows:
        table_rows = "".join(
            "<tr>"
            f"<td><a href=\"/companies/{quote(row['symbol'])}\">{escape(row['symbol'])}</a></td>"
            f"<td>{escape(row['market'])}</td>"
            f"<td>{escape(row['name'])}</td>"
            f"<td>{render_status_badge(row['data_status'])}</td>"
            f"<td>{escape(row['latest_period'] or '暂无')}</td>"
            f"<td>{int(row['period_count'])}</td>"
            "</tr>"
            for row in rows
        )
    else:
        table_rows = (
            "<tr><td colspan=\"6\">暂无公司。请先在顶部采集公司数据。</td></tr>"
        )
    return (
        "<div class=\"company-list-panel\"><section class=\"panel\">"
        "<div class=\"panel-header\"><div><h2>公司列表</h2>"
        f"<div class=\"muted\">已纳入 {company_count} 家公司</div></div>"
        "<a class=\"inline-action\" href=\"/companies\">查看全部</a></div>"
        "<div class=\"panel-body\">"
        "<table class=\"data-table\"><thead><tr>"
        "<th>代码</th><th>市场</th><th>公司</th><th>状态</th><th>最新期间</th><th>期间数</th>"
        "</tr></thead>"
        f"<tbody>{table_rows}</tbody></table>"
        "</div></section></div>"
    )


def render_dashboard(db_path: str | Path) -> str:
    stats = get_dashboard_stats(db_path)
    quality = stats["quality_counts"]
    body = (
        "<div class=\"research-dashboard\">"
        "<div class=\"page-title-row\"><div><h1>本地财务工作台</h1>"
        "<div class=\"muted\">只保留查询、采集、质量验证和导出前检查。</div></div>"
        "<form method=\"post\" action=\"/validate\"><button type=\"submit\">运行验证</button></form>"
        "</div>"
        f"{render_command_center()}"
        "<section class=\"metrics-row\">"
        f"<div class=\"metric\"><span class=\"metric-value\">{stats['company_count']}</span><span class=\"metric-label\">公司数量</span></div>"
        f"<div class=\"metric\"><span class=\"metric-value\">{quality['trusted'] + quality['usable']}</span><span class=\"metric-label\">AI 默认可导出</span></div>"
        f"<div class=\"metric\"><span class=\"metric-value\">{quality['needs_review']}</span><span class=\"metric-label\">需复核</span></div>"
        f"<div class=\"metric\"><span class=\"metric-value\">{stats['issue_count']}</span><span class=\"metric-label\">质量问题</span></div>"
        "</section>"
        f"{render_quality_summary(quality)}"
        f"{render_company_list_panel(db_path, int(stats['company_count']))}"
        "</div>"
    )
    return render_page("本地财务数据库", body)


def render_companies(db_path: str | Path) -> str:
    rows = queries.get_company_rows(db_path)
    coverage = queries.get_all_company_period_coverage(db_path)
    items = ""
    for row in rows:
        items += render_company_list_row(row, coverage.get(row["id"], []))
    if not items:
        items = "<div class=\"panel empty-state\">暂无公司。请先在顶部采集或刷新数据。</div>"
    body = (
        "<div class=\"page-title-row\"><div><h1>公司列表</h1>"
        "<div class=\"muted\">逐家公司检查已采集期间、已采集报表和缺失报表。</div></div></div>"
        "<section class=\"period-coverage-panel\">"
        "<div class=\"panel-header\"><div><h2>期间覆盖</h2>"
        "<div class=\"muted\">每家公司按报告期展示三大财报覆盖。</div></div></div>"
        f"<div class=\"company-page-list\">{items}</div>"
        "</section>"
    )
    return render_page("公司列表", body)


def render_company_coverage_items(periods: list[dict[str, object]]) -> str:
    if not periods:
        return "<li>暂无采集期间；缺失报表：利润表、资产负债表、现金流量表</li>"
    return "".join(
        "<li>"
        f"已采集期间：{escape(str(item['report_period']))}；"
        f"已采集报表：{escape('、'.join(_label(STATEMENT_LABELS, value) for value in item['statements']))}；"
        f"缺失报表：{escape('、'.join(_label(STATEMENT_LABELS, value) for value in item['missing']) or '无')}"
        "</li>"
        for item in periods
    )


def render_company_list_row(row, periods: list[dict[str, object]]) -> str:
    return (
        "<article class=\"panel company-row\">"
        "<div class=\"company-row-header\">"
        "<div>"
        f"<h2><a href=\"/companies/{quote(row['symbol'])}\">{escape(row['symbol'])}</a> "
        f"<span class=\"muted\">{escape(row['market'])}</span></h2>"
        f"<div class=\"muted\">{escape(row['name'])}</div>"
        "</div>"
        f"{render_status_badge(row['data_status'])}"
        "</div>"
        f"<ul class=\"coverage-list\">{render_company_coverage_items(periods)}</ul>"
        "</article>"
    )


def render_period_card(symbol: str, item: dict[str, object]) -> str:
    missing = item["missing"]
    statements = item["statements"]
    missing_text = "、".join(_label(STATEMENT_LABELS, value) for value in missing)
    statement_chips = "".join(
        f"<span class=\"chip\">{escape(_label(STATEMENT_LABELS, value))}</span>"
        for value in statements
    )
    missing_chip = (
        f"<span class=\"chip\">缺失：{escape(missing_text)}</span>"
        if missing
        else "<span class=\"chip\">缺失：无</span>"
    )
    return (
        "<a class=\"period-card\" "
        f"href=\"/companies/{quote(symbol)}?report_period={quote(str(item['report_period']))}\">"
        "<div class=\"period-title\">"
        f"<span>{escape(str(item['report_period']))}</span>"
        f"<span class=\"muted\">{3 - len(missing)}/3 张表</span>"
        "</div>"
        f"<div class=\"period-statements\">{statement_chips}{missing_chip}</div>"
        "</a>"
    )


def render_company_period_picker(
    symbol: str,
    periods: list[dict[str, object]],
) -> str:
    if periods:
        cards = "".join(render_period_card(symbol, item) for item in periods)
    else:
        cards = "<div class=\"empty-state\">暂无采集期间。请先采集或刷新结构化数据。</div>"
    return (
        "<section class=\"panel period-coverage-panel\">"
        "<div class=\"panel-header\"><div><h2>期间覆盖</h2>"
        "<div class=\"muted\">选择一个报告期后查看具体财务报表数据。</div></div></div>"
        f"<div class=\"panel-body period-grid\">{cards}</div>"
        "</section>"
    )


def render_company_header(company, subtitle: str, back_href: str, back_label: str) -> str:
    return (
        "<div class=\"page-title-row\"><div>"
        f"<h1>{escape(company['symbol'])} {escape(company['name'])}</h1>"
        f"<div class=\"muted\">{escape(subtitle)}</div></div>"
        f"<a class=\"inline-action\" href=\"{escape(back_href)}\">{escape(back_label)}</a>"
        "</div>"
    )


def render_company_summary(company, third_label: str, third_value: str) -> str:
    return (
        "<section class=\"detail-summary\">"
        f"<div class=\"summary-cell\"><span>市场</span><strong>{escape(company['market'])}</strong></div>"
        f"<div class=\"summary-cell\"><span>数据状态</span><strong>{render_status_badge(company['data_status'])}</strong></div>"
        f"<div class=\"summary-cell\"><span>{escape(third_label)}</span><strong>{escape(third_value)}</strong></div>"
        "</section>"
    )


def group_facts_by_statement(facts) -> dict[str, list[object]]:
    facts_by_statement: dict[str, list[object]] = {key: [] for key in STATEMENT_LABELS}
    for row in facts:
        if row["statement_type"] in facts_by_statement:
            facts_by_statement[row["statement_type"]].append(row)
    return facts_by_statement


def render_statement_rows(facts: list[object]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{escape(row['report_period'])}</td>"
        f"<td>{escape(_label(LINE_ITEM_LABELS, row['line_item']))}</td>"
        f"<td>{'' if row['value'] is None else escape(str(row['value']))}</td>"
        f"<td>{render_status_badge(row['quality_status'])}</td>"
        f"<td>{escape(row['source'] or '')}</td>"
        f"<td class=\"hash-cell\">{escape(row['payload_hash'] or '')}</td>"
        "</tr>"
        for row in facts
    )
    if rows:
        return rows
    return "<tr><td colspan=\"6\">暂无财务事实。请先运行 refresh 刷新结构化数据。</td></tr>"


def render_statement_tabs(facts) -> str:
    facts_by_statement = group_facts_by_statement(facts)
    tab_inputs = ""
    tab_labels = ""
    tab_panels = ""
    for index, (statement_type, statement_label) in enumerate(STATEMENT_LABELS.items()):
        checked = " checked" if index == 0 else ""
        rows = render_statement_rows(facts_by_statement[statement_type])
        tab_inputs += (
            f"<input type=\"radio\" name=\"statement-tab\" id=\"tab-{statement_type}\"{checked}>"
        )
        tab_labels += (
            f"<label class=\"statement-tab-label\" for=\"tab-{statement_type}\">"
            f"{escape(statement_label)}</label>"
        )
        tab_panels += (
            f"<section class=\"statement-panel\" id=\"panel-{statement_type}\">"
            f"<table class=\"data-table\" id=\"table-{statement_type}\">"
            "<thead><tr>"
            "<th>报告期</th><th>项目</th><th>数值</th><th>质量</th><th>来源</th><th>Payload Hash</th>"
            "</tr></thead>"
            f"<tbody>{rows}</tbody></table></section>"
        )
    return f"{tab_inputs}{tab_labels}{tab_panels}"


def normalize_requested_report_period(report_period: str) -> str:
    try:
        import normalizer

        normalized_period, _, _ = normalizer.normalize_report_period(report_period)
        return normalized_period
    except ValueError:
        return report_period


def render_company_detail(
    db_path: str | Path,
    symbol: str,
    *,
    report_period: str | None = None,
) -> tuple[int, str]:
    company = queries.get_company_by_symbol(db_path, symbol)
    if company is None:
        body = (
            "<div class=\"page-title-row\"><div><h1>未找到公司</h1>"
            "<div class=\"muted\">数据库里还没有这只股票。</div></div></div>"
            f"{render_stock_search_form(symbol.upper())}"
            "<div class=\"panel empty-state\">请先刷新数据，或确认 watchlist 中包含该股票代码。</div>"
        )
        return (
            404,
            render_page("未找到公司", body),
        )
    if not report_period:
        coverage = queries.get_company_period_coverage(db_path, int(company["id"]))
        body = (
            f"{render_company_header(company, '先选择报告期，再查看该期间的三大财务报表。', '/', '返回工作台')}"
            f"{render_company_summary(company, '已采集期间', str(len(coverage)))}"
            f"{render_company_period_picker(company['symbol'], coverage)}"
        )
        return 200, render_page(f"{company['symbol']} 期间覆盖", body)
    normalized_period = normalize_requested_report_period(report_period)
    facts = queries.get_company_facts(db_path, int(company["id"]), normalized_period)

    body = (
        f"{render_company_header(company, '公司财务事实按三大报表分标签展示。', '/companies', '返回公司列表')}"
        f"{render_company_summary(company, '当前财报期间', normalized_period)}"
        f"{render_period_filter_form(company['symbol'], normalized_period)}"
        "<section class=\"panel\">"
        "<div class=\"panel-header\"><div><h2>财报表格</h2>"
        "<div class=\"muted\">利润表、资产负债表、现金流量表分标签查看。</div></div></div>"
        "<div class=\"statement-tabs\">"
        f"{render_statement_tabs(facts)}"
        "</div></section>"
    )
    return 200, render_page(f"{company['symbol']} 财务报表", body)


def render_stock_search(
    db_path: str | Path,
    symbol: str,
    report_period: str | None = None,
) -> tuple[int, str]:
    normalized_symbol = (symbol or "").strip().upper()
    if not normalized_symbol:
        return 200, render_companies(db_path)
    return render_company_detail(
        db_path,
        normalized_symbol,
        report_period=report_period,
    )


def _looks_like_symbol(value: str) -> bool:
    normalized = value.strip().upper()
    return bool(
        re.fullmatch(r"\d{5,6}", normalized)
        or re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", normalized)
    )


def _infer_market(symbol: str, requested_market: str) -> str:
    requested = requested_market.strip().upper()
    if requested in {"US", "CN", "HK"}:
        return requested
    normalized = symbol.strip().upper()
    if re.fullmatch(r"\d{6}", normalized):
        return "CN"
    if re.fullmatch(r"\d{5}", normalized):
        return "HK"
    return "US"


def render_collect_result(
    db_path: str | Path,
    *,
    query: str,
    market: str = "auto",
    name: str = "",
    history_scope: str = "recent_5y",
    report_period: str = "",
    refresh_sources=None,
) -> tuple[int, str]:
    cleaned_query = query.strip()
    if not cleaned_query:
        body = (
            "<div class=\"page-title-row\"><div><h1>采集失败</h1>"
            "<div class=\"muted\">请输入公司名称或股票代码。</div></div></div>"
            f"{render_collect_form(query, market, name, history_scope, report_period)}"
        )
        return (
            400,
            render_page("采集失败", body),
        )

    matched = queries.find_company_by_query(db_path, cleaned_query)
    if matched is not None:
        company = WatchlistCompany(
            matched["symbol"],
            matched["market"],
            matched["name"],
            True,
        )
    elif _looks_like_symbol(cleaned_query):
        symbol = cleaned_query.upper()
        inferred_market = _infer_market(symbol, market)
        company = WatchlistCompany(
            symbol,
            inferred_market,
            name.strip() or symbol,
            True,
        )
    else:
        body = (
            "<div class=\"page-title-row\"><div><h1>无法仅凭公司名称采集</h1>"
            "<div class=\"muted\">这个名称还没有出现在本地数据库中。</div></div></div>"
            "<div class=\"panel empty-state\">请填写股票代码，并选择对应市场后再采集。</div>"
            f"{render_collect_form(cleaned_query, market, name, history_scope, report_period)}"
        )
        return (
            400,
            render_page("无法采集", body),
        )

    selected_period = report_period.strip() if history_scope == "period" else None
    summary = refresher.refresh_companies(
        db_path,
        [company],
        sources=refresh_sources,
        report_period=selected_period,
        history_scope=history_scope,
    )
    if summary["success_count"] == 0:
        body = (
            "<div class=\"page-title-row\"><div><h1>采集失败</h1>"
            f"<div class=\"muted\">{escape(str(summary))}</div></div></div>"
            f"{render_collect_form(cleaned_query, market, name, history_scope, report_period)}"
        )
        return (
            400,
            render_page("采集失败", body),
        )

    _, detail = render_company_detail(
        db_path,
        company.symbol,
        report_period=selected_period,
    )
    return (
        200,
        detail.replace(
            "<main class=\"page\">",
            "<main class=\"page\">"
            f"<div class=\"panel empty-state\"><strong>采集完成</strong><div>{escape(str(summary))}</div></div>",
            1,
        ),
    )


def render_validation_issues(db_path: str | Path) -> str:
    rows = queries.get_validation_issue_rows(db_path)
    items = render_validation_issue_rows(rows)
    body = (
        "<div class=\"page-title-row\"><div><h1>验证问题</h1>"
        "<div class=\"muted\">最近 100 条验证结果。</div></div>"
        "<form method=\"post\" action=\"/validate\"><button type=\"submit\">运行验证</button></form></div>"
        "<section class=\"panel\"><table class=\"data-table\"><thead><tr>"
        "<th>公司</th><th>规则</th><th>状态</th><th>消息</th>"
        f"</tr></thead><tbody>{items}</tbody></table></section>"
    )
    return render_page("验证问题", body)


def render_validation_issue_rows(rows) -> str:
    items = "".join(
        "<tr>"
        f"<td>{escape(row['symbol'])}</td>"
        f"<td>{escape(row['rule_name'])}</td>"
        f"<td>{escape(row['status'])}</td>"
        f"<td>{escape(row['message'])}</td>"
        "</tr>"
        for row in rows
    )
    return items or "<tr><td colspan=\"4\">暂无验证结果。</td></tr>"


def render_runs(db_path: str | Path) -> str:
    fetch_items = render_fetch_run_rows(queries.get_fetch_run_rows(db_path))
    crawler_items = render_crawler_run_rows(queries.get_crawler_run_rows(db_path))
    body = (
        "<div class=\"page-title-row\"><div><h1>运行记录</h1>"
        "<div class=\"muted\">刷新任务和披露补充任务的最近记录。</div></div></div>"
        "<section class=\"panel\"><div class=\"panel-header\"><h2>刷新任务</h2></div>"
        "<table class=\"data-table\"><thead><tr>"
        "<th>开始</th><th>结束</th><th>状态</th><th>成功</th><th>失败</th>"
        f"</tr></thead><tbody>{fetch_items}</tbody></table></section>"
        "<section class=\"panel\" style=\"margin-top:18px\"><div class=\"panel-header\"><h2>爬虫任务</h2></div>"
        "<table class=\"data-table\"><thead><tr>"
        "<th>开始</th><th>结束</th><th>状态</th><th>来源</th><th>消息</th>"
        f"</tr></thead><tbody>{crawler_items}</tbody></table></section>"
    )
    return render_page("运行记录", body)


def render_fetch_run_rows(fetch_runs) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{escape(row['started_at'])}</td>"
        f"<td>{escape(row['ended_at'] or '')}</td>"
        f"<td>{escape(_label(RUN_STATUS_LABELS, row['status']))}</td>"
        f"<td>{row['success_count']}</td>"
        f"<td>{row['failure_count']}</td>"
        "</tr>"
        for row in fetch_runs
    )
    return rows or "<tr><td colspan=\"5\">暂无刷新任务。</td></tr>"


def render_crawler_run_rows(crawler_runs) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{escape(row['started_at'])}</td>"
        f"<td>{escape(row['ended_at'] or '')}</td>"
        f"<td>{escape(row['status'])}</td>"
        f"<td>{escape(row['source_name'] or '')}</td>"
        f"<td>{escape(row['message'] or '')}</td>"
        "</tr>"
        for row in crawler_runs
    )
    return rows or "<tr><td colspan=\"5\">暂无爬虫任务。</td></tr>"


def render_export_page(db_path: str | Path) -> str:
    options = render_export_options(queries.get_export_company_rows(db_path))
    body = (
        "<div class=\"page-title-row\"><div><h1>导出</h1>"
        "<div class=\"muted\">默认导出 trusted 和 usable 财务事实。</div></div></div>"
        "<form class=\"form-card panel\" method=\"get\" action=\"/export\">"
        "<div class=\"form-grid\"><div class=\"field field-wide\">"
        "<label for=\"export-symbol\">公司</label>"
        f"<select id=\"export-symbol\" name=\"symbol\">{options}</select></div>"
        "<div class=\"field field-wide\"><button type=\"submit\">导出</button></div></div>"
        "</form>"
    )
    return render_page("导出", body)


def render_export_options(companies) -> str:
    return "".join(
        f"<option value=\"{escape(row['symbol'])}\">{escape(row['symbol'])} {escape(row['market'])} {escape(row['name'])}</option>"
        for row in companies
    )


def run_manual_validation(db_path: str | Path) -> str:
    summary = validator.run_validation(db_path)
    body = (
        "<div class=\"page-title-row\"><div><h1>验证完成</h1>"
        f"<div class=\"muted\">{escape(str(summary))}</div></div>"
        "<a class=\"inline-action\" href=\"/validation-issues\">查看验证问题</a></div>"
    )
    return render_page("验证完成", body)


def create_app(db_path: str | Path, *, refresh_sources=None):
    if FastAPI is None:
        return SimpleApp(db_path, refresh_sources=refresh_sources)

    app = FastAPI(title="Local Financial Database")
    app.state.db_path = str(db_path)
    app.state.dashboard_provider = lambda: get_dashboard_stats(db_path)
    app.state.http_get = lambda path: _dispatch_get(
        db_path, path, refresh_sources=refresh_sources
    )
    app.state.http_post = lambda path: _dispatch_post(db_path, path)

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        return render_dashboard(db_path)

    @app.get("/static/app.css")
    def app_css():
        return Response(read_static_css(), media_type="text/css")

    @app.get("/companies", response_class=HTMLResponse)
    def companies():
        return render_companies(db_path)

    @app.get("/search", response_class=HTMLResponse)
    def search(symbol: str = "", report_period: str = ""):
        status, html = render_stock_search(db_path, symbol, report_period)
        if status == 404:
            return HTMLResponse(html, status_code=404)
        return html

    @app.get("/collect", response_class=HTMLResponse)
    def collect(
        query: str = "",
        market: str = "auto",
        name: str = "",
        history_scope: str = "recent_5y",
        report_period: str = "",
    ):
        status, html = render_collect_result(
            db_path,
            query=query,
            market=market,
            name=name,
            history_scope=history_scope,
            report_period=report_period,
            refresh_sources=refresh_sources,
        )
        if status >= 400:
            return HTMLResponse(html, status_code=status)
        return html

    @app.get("/companies/{symbol}", response_class=HTMLResponse)
    def company_detail(symbol: str, report_period: str = ""):
        status, html = render_company_detail(
            db_path,
            symbol,
            report_period=report_period,
        )
        if status == 404:
            return HTMLResponse(html, status_code=404)
        return html

    @app.get("/validation-issues", response_class=HTMLResponse)
    def validation_issues():
        return render_validation_issues(db_path)

    @app.get("/runs", response_class=HTMLResponse)
    def runs():
        return render_runs(db_path)

    @app.get("/export", response_class=HTMLResponse)
    def export_page():
        return render_export_page(db_path)

    @app.post("/validate", response_class=HTMLResponse)
    def validate_now():
        return run_manual_validation(db_path)

    return app


def _dispatch_get(
    db_path: str | Path,
    path: str,
    *,
    refresh_sources=None,
) -> SimpleResponse:
    parsed = urlsplit(path)
    route_path = parsed.path
    query = parse_qs(parsed.query)
    if route_path == "/static/app.css":
        return SimpleResponse(200, read_static_css())
    if route_path == "/":
        return SimpleResponse(200, render_dashboard(db_path))
    if route_path == "/companies":
        return SimpleResponse(200, render_companies(db_path))
    if route_path == "/search":
        symbol = query.get("symbol", [""])[0]
        report_period = query.get("report_period", [""])[0]
        status, html = render_stock_search(db_path, symbol, report_period)
        return SimpleResponse(status, html)
    if route_path == "/collect":
        status, html = render_collect_result(
            db_path,
            query=query.get("query", [""])[0],
            market=query.get("market", ["auto"])[0],
            name=query.get("name", [""])[0],
            history_scope=query.get("history_scope", ["recent_5y"])[0],
            report_period=query.get("report_period", [""])[0],
            refresh_sources=refresh_sources,
        )
        return SimpleResponse(status, html)
    if route_path.startswith("/companies/"):
        status, html = render_company_detail(
            db_path,
            route_path.rsplit("/", 1)[-1],
            report_period=query.get("report_period", [""])[0],
        )
        return SimpleResponse(status, html)
    if route_path == "/validation-issues":
        return SimpleResponse(200, render_validation_issues(db_path))
    if route_path == "/runs":
        return SimpleResponse(200, render_runs(db_path))
    if route_path == "/export":
        return SimpleResponse(200, render_export_page(db_path))
    return SimpleResponse(404, "<html><body><h1>Not Found</h1></body></html>")


def _dispatch_post(db_path: str | Path, path: str) -> SimpleResponse:
    if path == "/validate":
        return SimpleResponse(200, run_manual_validation(db_path))
    return SimpleResponse(404, "<html><body><h1>Not Found</h1></body></html>")


class SimpleRoute:
    def __init__(self, path: str) -> None:
        self.path = path


class SimpleState:
    pass


class SimpleApp:
    def __init__(self, db_path: str | Path, *, refresh_sources=None) -> None:
        self.state = SimpleState()
        self.state.db_path = str(db_path)
        self.state.dashboard_provider = lambda: get_dashboard_stats(db_path)
        self.state.http_get = lambda path: _dispatch_get(
            db_path, path, refresh_sources=refresh_sources
        )
        self.state.http_post = lambda path: _dispatch_post(db_path, path)
        self.routes = [
            SimpleRoute("/"),
            SimpleRoute("/static/app.css"),
            SimpleRoute("/companies"),
            SimpleRoute("/search"),
            SimpleRoute("/collect"),
            SimpleRoute("/companies/{symbol}"),
            SimpleRoute("/validation-issues"),
            SimpleRoute("/runs"),
            SimpleRoute("/export"),
            SimpleRoute("/validate"),
        ]

