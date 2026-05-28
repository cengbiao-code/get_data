from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

import db


STATEMENT_TYPE_ALIASES = {
    "income": "income_statement",
    "income_statement": "income_statement",
    "balance": "balance_sheet",
    "balance_sheet": "balance_sheet",
    "cashflow": "cash_flow",
    "cash_flow": "cash_flow",
    "cash-flow": "cash_flow",
}
FACT_REQUIRED_FIELDS = ("statement_type", "report_period", "line_item")


class MissingFieldError(ValueError):
    def __init__(self, field: str) -> None:
        super().__init__(f"missing required field: {field}")
        self.field = field


def compute_payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def prepare_structured_payload(payload: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(payload)
    prepared.setdefault("source_url", None)
    prepared.setdefault("payload", {key: value for key, value in payload.items()})
    prepared["payload_hash"] = payload.get("payload_hash") or compute_payload_hash(
        prepared["payload"]
    )
    return prepared


def prepare_akshare_dataframe_payload(
    frame: Any,
    *,
    company_symbol: str,
    market: str,
    fetched_at: str,
    source_url: str | None = None,
) -> dict[str, Any]:
    facts = frame.where(frame.notna(), None).to_dict(orient="records")
    return prepare_structured_payload(
        {
            "company_symbol": company_symbol,
            "market": market,
            "source": "AKShare",
            "source_url": source_url,
            "source_confidence": "structured_open_source",
            "fetched_at": fetched_at,
            "facts": facts,
        }
    )


def normalize_statement_type(statement_type: str) -> str:
    normalized = STATEMENT_TYPE_ALIASES.get(statement_type.strip().lower())
    if normalized is None:
        raise ValueError(f"unsupported statement type: {statement_type}")
    return normalized


def normalize_report_period(report_period: str) -> tuple[str, int, str]:
    value = str(report_period).strip().upper()
    quarter_match = re.fullmatch(r"(\d{4})[-_/ ]?Q([1-4])", value)
    if quarter_match:
        year = int(quarter_match.group(1))
        quarter = f"Q{quarter_match.group(2)}"
        return f"{year}{quarter}", year, quarter

    annual_match = re.fullmatch(r"(\d{4})(?:[-_/ ]?FY|[-_/ ]?A)?", value)
    if annual_match:
        year = int(annual_match.group(1))
        return f"{year}FY", year, "FY"

    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%Y%m%d"):
        try:
            date_value = datetime.strptime(value, fmt)
        except ValueError:
            continue
        quarter_number = ((date_value.month - 1) // 3) + 1
        quarter = f"Q{quarter_number}"
        return f"{date_value.year}{quarter}", date_value.year, quarter

    raise ValueError(f"unsupported report period: {report_period}")


def validate_fact_fields(item: dict[str, Any]) -> None:
    for field in FACT_REQUIRED_FIELDS:
        if item.get(field) in (None, ""):
            raise MissingFieldError(field)


def normalize_mock_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return normalize_structured_payload(payload)


def normalize_structured_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    prepared = prepare_structured_payload(payload)
    facts = []
    for item in prepared.get("facts", []):
        validate_fact_fields(item)
        value = item.get("value")
        report_period, fiscal_year, fiscal_period = normalize_report_period(
            item["report_period"]
        )
        facts.append(
            {
                "company_symbol": prepared["company_symbol"],
                "market": prepared["market"],
                "statement_type": normalize_statement_type(item["statement_type"]),
                "report_period": report_period,
                "fiscal_year": item.get("fiscal_year", fiscal_year),
                "fiscal_period": item.get("fiscal_period", fiscal_period),
                "line_item": item["line_item"],
                "raw_line_item": item.get("raw_line_item", item["line_item"]),
                "value": None if value is None else float(value),
                "unit": item.get("unit"),
                "currency": item.get("currency"),
                "source": prepared["source"],
                "source_url": prepared.get("source_url"),
                "source_confidence": prepared["source_confidence"],
                "payload_hash": prepared["payload_hash"],
                "fetched_at": prepared["fetched_at"],
                "quality_status": item.get("quality_status", "needs_review"),
                "freshness_status": item.get("freshness_status", "unknown"),
                "validation_status": item.get("validation_status", "needs_review"),
            }
        )
    return facts


def record_empty_payload_issue(db_path: str, payload: dict[str, Any]) -> int:
    if payload.get("facts"):
        return 0
    db.insert_quality_issue(
        db_path,
        symbol=payload["company_symbol"],
        market=payload["market"],
        issue_type="empty_payload",
        severity="medium",
        message=f"{payload['source']} returned no structured financial facts",
    )
    return 1
