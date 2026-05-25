from __future__ import annotations

from pathlib import Path

from sources.disclosure_check import compare_structured_and_disclosed_periods

from .companies import get_company_id
from .connection import connect, utc_now


def insert_quality_issue(
    db_path: str | Path,
    *,
    symbol: str,
    market: str,
    issue_type: str,
    severity: str,
    message: str,
    report_period: str | None = None,
) -> None:
    now = utc_now()
    with connect(db_path) as conn:
        company_id = None
        row = conn.execute(
            "select id from companies where symbol = ? and market = ?",
            (symbol, market),
        ).fetchone()
        if row:
            company_id = row["id"]
        conn.execute(
            """
            insert into quality_issues(
                company_id, symbol, market, issue_type, severity, message,
                report_period, created_at
            )
            values(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                symbol,
                market,
                issue_type,
                severity,
                message,
                report_period,
                now,
            ),
        )
        conn.commit()


def upsert_data_freshness(
    db_path: str | Path,
    *,
    symbol: str,
    market: str,
    latest_structured_period: str | None,
    latest_disclosure_period: str | None,
    latest_disclosure_date: str | None = None,
) -> str:
    status = compare_structured_and_disclosed_periods(
        latest_structured_period, latest_disclosure_period
    )
    checked_at = utc_now()
    with connect(db_path) as conn:
        company_id = get_company_id(conn, symbol, market)
        conn.execute(
            """
            insert into data_freshness(
                company_id, latest_structured_period, latest_disclosure_period,
                latest_disclosure_date, freshness_status, checked_at
            )
            values(?, ?, ?, ?, ?, ?)
            on conflict(company_id) do update set
                latest_structured_period = excluded.latest_structured_period,
                latest_disclosure_period = excluded.latest_disclosure_period,
                latest_disclosure_date = excluded.latest_disclosure_date,
                freshness_status = excluded.freshness_status,
                checked_at = excluded.checked_at
            """,
            (
                company_id,
                latest_structured_period,
                latest_disclosure_period,
                latest_disclosure_date,
                status,
                checked_at,
            ),
        )
        conn.commit()

    if status in {"stale", "pending_structured_data"}:
        insert_quality_issue(
            db_path,
            symbol=symbol,
            market=market,
            issue_type="pending_structured_data",
            severity="medium",
            message=(
                "Structured financial data lags latest disclosure period "
                f"{latest_disclosure_period}"
            ),
            report_period=latest_disclosure_period,
        )

    return status


def _period_sort_key(report_period: str) -> tuple[int, int]:
    value = report_period.strip().upper()
    if value.endswith("FY"):
        return int(value[:4]), 5
    if "Q" in value:
        year, quarter = value.split("Q", 1)
        return int(year), int(quarter)
    return int(value[:4]), 0


def refresh_freshness_from_facts(
    db_path: str | Path,
    *,
    symbol: str,
    market: str,
    latest_disclosure_period: str | None,
    latest_disclosure_date: str | None = None,
) -> str:
    with connect(db_path) as conn:
        company_id = get_company_id(conn, symbol, market)
        rows = conn.execute(
            """
            select distinct report_period
            from financial_facts
            where company_id = ?
            """,
            (company_id,),
        ).fetchall()
    latest_structured_period = None
    if rows:
        latest_structured_period = max(
            (row["report_period"] for row in rows), key=_period_sort_key
        )
    return upsert_data_freshness(
        db_path,
        symbol=symbol,
        market=market,
        latest_structured_period=latest_structured_period,
        latest_disclosure_period=latest_disclosure_period,
        latest_disclosure_date=latest_disclosure_date,
    )


def refresh_freshness_from_disclosure_events(
    db_path: str | Path,
    *,
    symbol: str,
    market: str,
) -> str:
    with connect(db_path) as conn:
        company_id = get_company_id(conn, symbol, market)
        rows = conn.execute(
            """
            select report_period, disclosure_date
            from disclosure_events
            where company_id = ?
              and report_period is not null
            """,
            (company_id,),
        ).fetchall()

    latest_disclosure_period = None
    latest_disclosure_date = None
    if rows:
        latest = max(rows, key=lambda row: _period_sort_key(row["report_period"]))
        latest_disclosure_period = latest["report_period"]
        latest_disclosure_date = latest["disclosure_date"]

    return refresh_freshness_from_facts(
        db_path,
        symbol=symbol,
        market=market,
        latest_disclosure_period=latest_disclosure_period,
        latest_disclosure_date=latest_disclosure_date,
    )
