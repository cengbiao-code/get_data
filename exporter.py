from __future__ import annotations

import csv
import json
from pathlib import Path

import db
from models import EXPORT_DEFAULT_STATUSES


EXPORT_FIELDS = [
    "company_symbol",
    "market",
    "statement_type",
    "report_period",
    "fiscal_year",
    "fiscal_period",
    "line_item",
    "raw_line_item",
    "value",
    "unit",
    "currency",
    "source",
    "source_url",
    "source_confidence",
    "payload_hash",
    "fetched_at",
    "freshness_status",
    "validation_status",
    "quality_status",
    "quality_score",
]


def _query_rows(
    db_path: str | Path,
    *,
    symbol: str | None,
    report_period: str | None,
    statuses: list[str],
) -> list[dict[str, object]]:
    placeholders = ", ".join("?" for _ in statuses)
    params: list[object] = list(statuses)
    where = [f"ff.quality_status in ({placeholders})"]
    if symbol:
        where.append("ff.company_symbol = ?")
        params.append(symbol.upper())
    if report_period:
        where.append("ff.report_period = ?")
        params.append(report_period.upper())

    query = f"""
        select
            ff.company_symbol,
            ff.market,
            ff.statement_type,
            ff.report_period,
            ff.fiscal_year,
            ff.fiscal_period,
            ff.line_item,
            ff.raw_line_item,
            ff.value,
            ff.unit,
            ff.currency,
            ff.source,
            ff.source_url,
            ff.source_confidence,
            ff.payload_hash,
            ff.fetched_at,
            ff.freshness_status,
            ff.validation_status,
            ff.quality_status,
            coalesce(dqs.score, 0) as quality_score
        from financial_facts ff
        left join data_quality_scores dqs
            on dqs.company_id = ff.company_id and dqs.scope = 'company'
        where {" and ".join(where)}
        order by ff.company_symbol, ff.report_period, ff.statement_type, ff.line_item
    """
    with db.connect(db_path) as conn:
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def export_facts(
    db_path: str | Path,
    out_dir: str | Path,
    *,
    symbol: str | None = None,
    report_period: str | None = None,
    formats: list[str] | None = None,
    statuses: list[str] | None = None,
) -> dict[str, Path]:
    selected_formats = formats or ["csv"]
    selected_statuses = statuses or list(EXPORT_DEFAULT_STATUSES)
    rows = _query_rows(
        db_path,
        symbol=symbol,
        report_period=report_period,
        statuses=selected_statuses,
    )
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    stem = symbol.upper() if symbol else "financial_facts"
    if report_period:
        stem = f"{stem}_{report_period.upper()}"
    written: dict[str, Path] = {}
    if "csv" in selected_formats:
        csv_path = target / f"{stem}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=EXPORT_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        written["csv"] = csv_path

    if "jsonl" in selected_formats:
        jsonl_path = target / f"{stem}.jsonl"
        with jsonl_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        written["jsonl"] = jsonl_path

    return written
