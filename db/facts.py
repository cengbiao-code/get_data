from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .companies import get_company_id
from .connection import connect


def insert_raw_payload(db_path: str | Path, payload: dict[str, Any]) -> int:
    with connect(db_path) as conn:
        company_id = get_company_id(conn, payload["company_symbol"], payload["market"])
        cursor = conn.execute(
            """
            insert into raw_payloads(
                company_id, source, source_url, source_confidence, payload_hash,
                payload_json, fetched_at, fetch_run_id
            )
            values(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                payload["source"],
                payload.get("source_url"),
                payload["source_confidence"],
                payload["payload_hash"],
                json.dumps(payload["payload"], ensure_ascii=False, sort_keys=True),
                payload["fetched_at"],
                payload.get("fetch_run_id"),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def insert_financial_fact(db_path: str | Path, fact: dict[str, Any]) -> int:
    with connect(db_path) as conn:
        company_id = get_company_id(conn, fact["company_symbol"], fact["market"])
        duplicate_count = conn.execute(
            """
            select count(*) from financial_facts
            where company_id = ?
              and statement_type = ?
              and report_period = ?
              and line_item = ?
            """,
            (
                company_id,
                fact["statement_type"],
                fact["report_period"],
                fact["line_item"],
            ),
        ).fetchone()[0]
        version = int(duplicate_count) + 1
        cursor = conn.execute(
            """
            insert into financial_facts(
                company_id, company_symbol, market, statement_type, report_period,
                fiscal_year, fiscal_period, line_item, raw_line_item, value, unit,
                currency, source, source_url, source_confidence, payload_hash,
                fetched_at, quality_status, freshness_status, validation_status,
                version
            )
            values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                fact["company_symbol"],
                fact["market"],
                fact["statement_type"],
                fact["report_period"],
                fact.get("fiscal_year"),
                fact.get("fiscal_period"),
                fact["line_item"],
                fact.get("raw_line_item"),
                fact.get("value"),
                fact.get("unit"),
                fact.get("currency"),
                fact["source"],
                fact.get("source_url"),
                fact["source_confidence"],
                fact["payload_hash"],
                fact["fetched_at"],
                fact.get("quality_status", "needs_review"),
                fact.get("freshness_status", "unknown"),
                fact.get("validation_status", "needs_review"),
                version,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
