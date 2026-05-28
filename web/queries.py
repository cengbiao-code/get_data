from __future__ import annotations

from pathlib import Path

import db


EXPECTED_STATEMENTS = {"income_statement", "balance_sheet", "cash_flow"}


def get_dashboard_stats(db_path: str | Path) -> dict[str, object]:
    with db.connect(db_path) as conn:
        company_count = conn.execute("select count(*) from companies").fetchone()[0]
        quality_counts = {
            status: 0 for status in ("trusted", "usable", "needs_review", "stale", "failed")
        }
        for row in conn.execute(
            "select data_status, count(*) as n from companies group by data_status"
        ):
            quality_counts[row["data_status"]] = int(row["n"])
        issue_count = conn.execute("select count(*) from quality_issues").fetchone()[0]
    return {
        "company_count": int(company_count),
        "quality_counts": quality_counts,
        "issue_count": int(issue_count),
    }


def get_company_list_summary_rows(db_path: str | Path):
    with db.connect(db_path) as conn:
        return conn.execute(
            """
            select c.id, c.symbol, c.market, c.name, c.data_status,
                   max(ff.report_period) as latest_period,
                   count(distinct ff.report_period) as period_count
            from companies c
            left join financial_facts ff on ff.company_id = c.id
            group by c.id, c.symbol, c.market, c.name, c.data_status
            order by c.market, c.symbol
            """
        ).fetchall()


def get_company_rows(db_path: str | Path):
    with db.connect(db_path) as conn:
        return conn.execute(
            """
            select id, symbol, market, name, data_status
            from companies
            order by market, symbol
            """
        ).fetchall()


def get_all_company_period_coverage(db_path: str | Path) -> dict[int, list[dict[str, object]]]:
    with db.connect(db_path) as conn:
        rows = conn.execute(
            """
            select company_id, report_period, statement_type
            from financial_facts
            group by company_id, report_period, statement_type
            order by report_period desc, statement_type
            """
        ).fetchall()
    coverage: dict[int, dict[str, set[str]]] = {}
    for row in rows:
        company_periods = coverage.setdefault(row["company_id"], {})
        statements = company_periods.setdefault(row["report_period"], set())
        statements.add(row["statement_type"])
    return {
        company_id: [
            {
                "report_period": period,
                "statements": sorted(statements),
                "missing": sorted(EXPECTED_STATEMENTS - statements),
            }
            for period, statements in periods.items()
        ]
        for company_id, periods in coverage.items()
    }


def find_company_by_query(db_path: str | Path, query: str):
    normalized_query = query.strip().upper()
    with db.connect(db_path) as conn:
        row = conn.execute(
            """
            select symbol, market, name
            from companies
            where upper(symbol) = ? or lower(name) = lower(?)
            order by market, symbol
            limit 1
            """,
            (normalized_query, query.strip()),
        ).fetchone()
        if row is not None:
            return row
        return conn.execute(
            """
            select symbol, market, name
            from companies
            where lower(name) like lower(?)
            order by market, symbol
            limit 1
            """,
            (f"%{query.strip()}%",),
        ).fetchone()


def get_company_by_symbol(db_path: str | Path, symbol: str):
    with db.connect(db_path) as conn:
        return conn.execute(
            """
            select id, symbol, market, name, data_status
            from companies
            where symbol = ?
            """,
            (symbol.upper(),),
        ).fetchone()


def get_company_period_coverage(
    db_path: str | Path,
    company_id: int,
) -> list[dict[str, object]]:
    with db.connect(db_path) as conn:
        rows = conn.execute(
            """
            select report_period, statement_type
            from financial_facts
            where company_id = ?
            group by report_period, statement_type
            order by report_period desc, statement_type
            """,
            (company_id,),
        ).fetchall()
    periods: dict[str, set[str]] = {}
    for row in rows:
        periods.setdefault(row["report_period"], set()).add(row["statement_type"])
    return [
        {
            "report_period": period,
            "statements": sorted(statements),
            "missing": sorted(EXPECTED_STATEMENTS - statements),
        }
        for period, statements in periods.items()
    ]


def get_company_facts(
    db_path: str | Path,
    company_id: int,
    report_period: str,
):
    with db.connect(db_path) as conn:
        return conn.execute(
            """
            select statement_type, report_period, line_item, value, quality_status,
                   source, payload_hash
            from financial_facts
            where company_id = ?
              and report_period = ?
            order by report_period desc, statement_type, line_item
            limit 200
            """,
            (company_id, report_period),
        ).fetchall()


def get_validation_issue_rows(db_path: str | Path):
    with db.connect(db_path) as conn:
        return conn.execute(
            """
            select coalesce(c.symbol, '') as symbol, vr.rule_name, vr.status, vr.message
            from validation_results vr
            left join companies c on c.id = vr.company_id
            order by vr.checked_at desc
            limit 100
            """
        ).fetchall()


def get_validation_result_rows(
    db_path: str | Path,
    *,
    symbol: str | None = None,
    report_period: str | None = None,
):
    filters = []
    params: list[object] = []
    if symbol:
        filters.append("c.symbol = ?")
        params.append(symbol.upper())
    if report_period:
        filters.append("(vr.report_period = ? or vr.report_period is null)")
        params.append(report_period.upper())
    where = f"where {' and '.join(filters)}" if filters else ""
    with db.connect(db_path) as conn:
        return conn.execute(
            f"""
            select coalesce(c.symbol, '') as symbol, vr.rule_name, vr.status,
                   vr.severity, vr.message, vr.report_period, vr.checked_at
            from validation_results vr
            left join companies c on c.id = vr.company_id
            {where}
            order by
                case vr.status when 'failed' then 0 when 'warning' then 1 else 2 end,
                vr.rule_name
            """,
            params,
        ).fetchall()


def get_fetch_run_rows(db_path: str | Path):
    with db.connect(db_path) as conn:
        return conn.execute(
            """
            select started_at, ended_at, status, success_count, failure_count
            from fetch_runs
            order by id desc
            limit 50
            """
        ).fetchall()


def get_crawler_run_rows(db_path: str | Path):
    with db.connect(db_path) as conn:
        return conn.execute(
            """
            select started_at, ended_at, status, source_name, message
            from crawler_runs
            order by id desc
            limit 50
            """
        ).fetchall()


def get_export_company_rows(db_path: str | Path):
    with db.connect(db_path) as conn:
        return conn.execute(
            "select symbol, market, name from companies order by market, symbol"
        ).fetchall()


def get_export_period_rows(db_path: str | Path):
    with db.connect(db_path) as conn:
        return conn.execute(
            """
            select distinct report_period
            from financial_facts
            order by report_period desc
            """
        ).fetchall()
