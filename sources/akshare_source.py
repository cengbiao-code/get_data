from __future__ import annotations

from typing import Any

import db


class AKShareSourceError(RuntimeError):
    pass


class AKShareClient:
    statement_labels = {
        "income_statement": "利润表",
        "balance_sheet": "资产负债表",
        "cash_flow": "现金流量表",
    }

    def fetch_statement(self, symbol: str, market: str, statement_type: str):
        try:
            import akshare as ak
        except ModuleNotFoundError as exc:
            raise AKShareSourceError("akshare is not installed") from exc

        # The adapter keeps live AKShare calls behind this thin seam. Exact
        # function names can vary by market/API version, so tests use injection.
        function_name = {
            ("CN", "income_statement"): "stock_financial_report_sina",
            ("CN", "balance_sheet"): "stock_financial_report_sina",
            ("CN", "cash_flow"): "stock_financial_report_sina",
            ("HK", "income_statement"): "stock_financial_hk_report_em",
            ("HK", "balance_sheet"): "stock_financial_hk_report_em",
            ("HK", "cash_flow"): "stock_financial_hk_report_em",
        }.get((market, statement_type))
        if function_name is None or not hasattr(ak, function_name):
            raise AKShareSourceError(
                f"AKShare function not configured for {market} {statement_type}"
            )
        function = getattr(ak, function_name)
        label = self.statement_labels[statement_type]
        if market == "CN":
            return function(stock=self._cn_symbol(symbol), symbol=label)
        if market == "HK":
            try:
                return function(stock=symbol, symbol=label, indicator="年度")
            except TypeError:
                return function(stock=symbol, symbol=label)
        return function(stock=symbol)

    def _cn_symbol(self, symbol: str) -> str:
        if symbol.startswith(("sh", "sz", "bj")):
            return symbol
        if symbol.startswith("6"):
            return f"sh{symbol}"
        if symbol.startswith(("0", "3")):
            return f"sz{symbol}"
        return symbol


class AKShareSource:
    source_name = "AKShare"
    source_confidence = "structured_open_source"
    statement_types = ("income_statement", "balance_sheet", "cash_flow")
    report_period_columns = (
        "report_period",
        "date",
        "报告期",
        "报表日期",
        "报告日",
        "REPORT_DATE",
        "STD_REPORT_DATE",
    )
    ignored_wide_columns = {"公告日期", "币种", "currency", "unit"}
    line_item_aliases = {
        "营业收入": "revenue",
        "营业总收入": "revenue",
        "净利润": "net_income",
        "归属于母公司所有者的净利润": "net_income",
        "资产总计": "total_assets",
        "负债合计": "total_liabilities",
        "所有者权益(或股东权益)合计": "total_equity",
        "所有者权益合计": "total_equity",
        "股东权益合计": "total_equity",
        "经营活动产生的现金流量净额": "operating_cash_flow",
    }

    def __init__(self, *, client: Any | None = None, fetched_at: str | None = None) -> None:
        self.client = client or AKShareClient()
        self.fetched_at = fetched_at

    def fetch_financial_reports(self, symbol: str, market: str) -> dict[str, Any]:
        statements = {}
        for statement_type in self.statement_types:
            try:
                statements[statement_type] = self.client.fetch_statement(
                    symbol, market, statement_type
                )
            except Exception as exc:
                if isinstance(exc, AKShareSourceError):
                    raise
                raise AKShareSourceError(
                    f"failed to fetch AKShare {market} {statement_type} for {symbol}: {exc}"
                ) from exc
        return statements

    def fetch(self, company) -> dict[str, Any]:
        statements = self.fetch_financial_reports(company.symbol, company.market)
        facts = []
        payload_statements = {}
        for statement_type, frame in statements.items():
            rows = self._frame_to_rows(frame, statement_type)
            facts.extend(rows)
            payload_statements[statement_type] = rows
        return {
            "company_symbol": company.symbol,
            "market": company.market,
            "source": self.source_name,
            "source_url": None,
            "source_confidence": self.source_confidence,
            "fetched_at": self.fetched_at or db.utc_now(),
            "facts": facts,
            "payload": {"statements": payload_statements},
        }

    def _frame_to_rows(self, frame: Any, statement_type: str) -> list[dict[str, Any]]:
        if frame is None or getattr(frame, "empty", False):
            return []
        rows = frame.where(frame.notna(), None).to_dict(orient="records")
        if rows and not any("line_item" in row or "项目" in row for row in rows):
            if any("STD_ITEM_NAME" in row and "AMOUNT" in row for row in rows):
                return self._standard_long_rows_to_facts(rows, statement_type)
            return self._wide_rows_to_facts(rows, statement_type)
        converted = []
        for row in rows:
            converted.append(
                {
                    "statement_type": row.get("statement_type", statement_type),
                    "report_period": row.get("report_period")
                    or row.get("date")
                    or row.get("报告期")
                    or row.get("报表日期"),
                    "line_item": row.get("line_item") or row.get("item") or row.get("项目"),
                    "raw_line_item": row.get("raw_line_item")
                    or row.get("item")
                    or row.get("项目")
                    or row.get("line_item"),
                    "value": row.get("value") if "value" in row else row.get("金额"),
                    "unit": row.get("unit"),
                    "currency": row.get("currency"),
                    "quality_status": row.get("quality_status", "usable"),
                    "freshness_status": row.get("freshness_status", "unknown"),
                    "validation_status": row.get("validation_status", "needs_review"),
                }
            )
        return converted

    def _standard_long_rows_to_facts(
        self, rows: list[dict[str, Any]], statement_type: str
    ) -> list[dict[str, Any]]:
        converted = []
        for row in rows:
            report_period = self._pick_first(row, self.report_period_columns)
            raw_line_item = row.get("STD_ITEM_NAME")
            numeric_value = self._coerce_number(row.get("AMOUNT"))
            if report_period in (None, "") or not raw_line_item or numeric_value is None:
                continue
            converted.append(
                {
                    "statement_type": statement_type,
                    "report_period": report_period,
                    "line_item": self.line_item_aliases.get(raw_line_item, str(raw_line_item)),
                    "raw_line_item": str(raw_line_item),
                    "value": numeric_value,
                    "unit": row.get("unit"),
                    "currency": row.get("currency"),
                    "quality_status": "usable",
                    "freshness_status": "unknown",
                    "validation_status": "needs_review",
                }
            )
        return converted

    def _wide_rows_to_facts(
        self, rows: list[dict[str, Any]], statement_type: str
    ) -> list[dict[str, Any]]:
        converted = []
        for row in rows:
            report_period = self._pick_first(row, self.report_period_columns)
            if report_period in (None, ""):
                continue
            for column, value in row.items():
                if column in self.report_period_columns or column in self.ignored_wide_columns:
                    continue
                if value in (None, ""):
                    continue
                numeric_value = self._coerce_number(value)
                if numeric_value is None:
                    continue
                converted.append(
                    {
                        "statement_type": statement_type,
                        "report_period": report_period,
                        "line_item": self.line_item_aliases.get(column, str(column)),
                        "raw_line_item": str(column),
                        "value": numeric_value,
                        "unit": row.get("unit"),
                        "currency": row.get("currency") or row.get("币种"),
                        "quality_status": "usable",
                        "freshness_status": "unknown",
                        "validation_status": "needs_review",
                    }
                )
        return converted

    def _pick_first(self, row: dict[str, Any], keys: tuple[str, ...]):
        for key in keys:
            if row.get(key) not in (None, ""):
                return row[key]
        return None

    def _coerce_number(self, value):
        if isinstance(value, str):
            cleaned = value.replace(",", "").strip()
            if cleaned in {"--", "-", ""}:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return value
