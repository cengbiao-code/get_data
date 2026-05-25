from __future__ import annotations

from pathlib import Path

import db
from models import STATEMENT_TYPES


KEY_FIELDS = {
    "income_statement": ("revenue", "net_income"),
    "balance_sheet": ("total_assets", "total_liabilities", "total_equity"),
    "cash_flow": ("operating_cash_flow",),
}
KEY_FIELD_RULES = {
    "income_statement": "key_income_fields_present",
    "balance_sheet": "key_balance_fields_present",
    "cash_flow": "key_cash_flow_fields_present",
}
LARGE_CHANGE_MULTIPLE = 5


def _clear_prior_results(conn, checked_at: str) -> None:
    conn.execute("delete from validation_results")
    conn.execute("delete from data_quality_scores")


def _write_result(
    conn,
    *,
    company_id: int,
    rule_name: str,
    status: str,
    severity: str,
    message: str,
    checked_at: str,
    report_period: str | None = None,
) -> None:
    conn.execute(
        """
        insert into validation_results(
            company_id, rule_name, status, severity, message, report_period, checked_at
        )
        values(?, ?, ?, ?, ?, ?, ?)
        """,
        (company_id, rule_name, status, severity, message, report_period, checked_at),
    )


def _quality_from_failures(error_count: int, warning_count: int) -> tuple[int, str]:
    if error_count > 0:
        return 30, "failed"
    if warning_count >= 2:
        return 55, "needs_review"
    if warning_count > 0:
        return 80, "usable"
    return 95, "trusted"


def _validate_key_fields(conn, company_id: int, facts, checked_at: str) -> int:
    warnings = 0
    for statement_type, required_fields in KEY_FIELDS.items():
        statement_facts = [
            fact for fact in facts if fact["statement_type"] == statement_type
        ]
        if not statement_facts:
            continue
        present_fields = {
            fact["line_item"] for fact in statement_facts if fact["value"] is not None
        }
        missing = sorted(set(required_fields) - present_fields)
        if missing:
            warnings += 1
            _write_result(
                conn,
                company_id=company_id,
                rule_name=KEY_FIELD_RULES[statement_type],
                status="warning",
                severity="medium",
                message="Missing key fields: " + ", ".join(missing),
                checked_at=checked_at,
            )
    return warnings


def _validate_balance_sheet(conn, company_id: int, facts, checked_at: str) -> int:
    warnings = 0
    balance_facts = [fact for fact in facts if fact["statement_type"] == "balance_sheet"]
    periods = sorted({fact["report_period"] for fact in balance_facts})
    for period in periods:
        values = {
            fact["line_item"]: fact["value"]
            for fact in balance_facts
            if fact["report_period"] == period and fact["value"] is not None
        }
        required = ("total_assets", "total_liabilities", "total_equity")
        if not all(item in values for item in required):
            continue
        assets = float(values["total_assets"])
        liabilities = float(values["total_liabilities"])
        equity = float(values["total_equity"])
        tolerance = max(abs(assets), abs(liabilities + equity), 1.0) * 0.01
        if abs(assets - liabilities - equity) > tolerance:
            warnings += 1
            _write_result(
                conn,
                company_id=company_id,
                rule_name="balance_sheet_balances",
                status="warning",
                severity="high",
                message=(
                    f"Balance sheet does not balance for {period}: "
                    f"assets={assets}, liabilities={liabilities}, equity={equity}"
                ),
                report_period=period,
                checked_at=checked_at,
            )
    return warnings


def _validate_large_changes(conn, company_id: int, facts, checked_at: str) -> int:
    warnings = 0
    grouped: dict[tuple[str, str], list] = {}
    for fact in facts:
        if fact["value"] is None:
            continue
        key = (fact["statement_type"], fact["line_item"])
        grouped.setdefault(key, []).append(fact)

    for (_statement_type, line_item), rows in grouped.items():
        ordered = sorted(rows, key=lambda row: (row["report_period"], row["version"]))
        previous = None
        for row in ordered:
            value = float(row["value"])
            if previous is not None and previous != 0:
                change_multiple = abs(value - previous) / abs(previous)
                if change_multiple > LARGE_CHANGE_MULTIPLE:
                    warnings += 1
                    _write_result(
                        conn,
                        company_id=company_id,
                        rule_name="large_change_detected",
                        status="warning",
                        severity="medium",
                        message=(
                            f"Large change detected for {line_item}: "
                            f"previous={previous}, current={value}"
                        ),
                        report_period=row["report_period"],
                        checked_at=checked_at,
                    )
                    break
            previous = value
    return warnings


def _validate_payload_revisions(conn, company_id: int, checked_at: str) -> int:
    revision_rows = conn.execute(
        """
        select report_period, statement_type, line_item, count(distinct payload_hash) as n
        from financial_facts
        where company_id = ?
        group by report_period, statement_type, line_item
        having count(distinct payload_hash) > 1
        """,
        (company_id,),
    ).fetchall()
    for row in revision_rows:
        _write_result(
            conn,
            company_id=company_id,
            rule_name="payload_revision_detected",
            status="warning",
            severity="low",
            message=(
                "Payload hash changed for "
                f"{row['statement_type']} {row['line_item']} {row['report_period']}"
            ),
            report_period=row["report_period"],
            checked_at=checked_at,
        )
    return len(revision_rows)


def run_validation(db_path: str | Path) -> dict[str, int]:
    checked_at = db.utc_now()
    companies_checked = 0
    results_written = 0
    with db.connect(db_path) as conn:
        _clear_prior_results(conn, checked_at)
        companies = conn.execute(
            "select id, symbol, market from companies where enabled = 1"
        ).fetchall()

        for company in companies:
            companies_checked += 1
            company_id = int(company["id"])
            facts = conn.execute(
                "select * from financial_facts where company_id = ?",
                (company_id,),
            ).fetchall()
            error_count = 0
            warning_count = 0

            if not facts:
                warning_count += 1
                _write_result(
                    conn,
                    company_id=company_id,
                    rule_name="three_statements_present",
                    status="warning",
                    severity="medium",
                    message="No financial facts found for enabled company",
                    checked_at=checked_at,
                )
                results_written += 1
            else:
                present = {fact["statement_type"] for fact in facts}
                missing = sorted(set(STATEMENT_TYPES) - present)
                if missing:
                    warning_count += 1
                    _write_result(
                        conn,
                        company_id=company_id,
                        rule_name="three_statements_present",
                        status="warning",
                        severity="medium",
                        message="Missing statements: " + ", ".join(missing),
                        checked_at=checked_at,
                    )
                    results_written += 1

                for field, rule in (
                    ("source", "source_required"),
                    ("fetched_at", "fetched_at_required"),
                    ("payload_hash", "payload_hash_required"),
                ):
                    missing_count = sum(1 for fact in facts if not fact[field])
                    if missing_count:
                        error_count += 1
                        _write_result(
                            conn,
                            company_id=company_id,
                            rule_name=rule,
                            status="failed",
                            severity="high",
                            message=f"{missing_count} facts missing {field}",
                            checked_at=checked_at,
                        )
                        results_written += 1

                stale_count = sum(
                    1
                    for fact in facts
                    if fact["quality_status"] == "stale"
                    or fact["freshness_status"] == "stale"
                )
                if stale_count:
                    warning_count += 1
                    _write_result(
                        conn,
                        company_id=company_id,
                        rule_name="freshness_current_or_marked",
                        status="warning",
                        severity="medium",
                        message=f"{stale_count} facts are marked stale",
                        checked_at=checked_at,
                    )
                    results_written += 1

                duplicate_rows = conn.execute(
                    """
                    select report_period, statement_type, line_item, count(*) as n
                    from financial_facts
                    where company_id = ?
                    group by report_period, statement_type, line_item
                    having count(*) > 1
                    """,
                    (company_id,),
                ).fetchall()
                if duplicate_rows:
                    warning_count += 1
                    _write_result(
                        conn,
                        company_id=company_id,
                        rule_name="duplicate_period_detected",
                        status="warning",
                        severity="low",
                        message=f"{len(duplicate_rows)} duplicate period rows detected",
                        checked_at=checked_at,
                    )
                    results_written += 1

                key_field_warnings = _validate_key_fields(
                    conn, company_id, facts, checked_at
                )
                warning_count += key_field_warnings
                results_written += key_field_warnings

                balance_warnings = _validate_balance_sheet(
                    conn, company_id, facts, checked_at
                )
                warning_count += balance_warnings
                results_written += balance_warnings

                large_change_warnings = _validate_large_changes(
                    conn, company_id, facts, checked_at
                )
                warning_count += large_change_warnings
                results_written += large_change_warnings

                revision_warnings = _validate_payload_revisions(
                    conn, company_id, checked_at
                )
                warning_count += revision_warnings
                results_written += revision_warnings

            score, status = _quality_from_failures(error_count, warning_count)
            conn.execute(
                """
                insert into data_quality_scores(
                    company_id, scope, report_period, score, quality_status,
                    calculated_at
                )
                values(?, 'company', null, ?, ?, ?)
                """,
                (company_id, score, status, checked_at),
            )
            conn.execute(
                """
                update companies
                set data_status = ?, updated_at = ?
                where id = ?
                """,
                (status, checked_at, company_id),
            )

        conn.commit()

    return {"companies_checked": companies_checked, "results_written": results_written}
