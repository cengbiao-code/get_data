from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import re
from typing import Protocol

import db
import errors
import normalizer
import validator
from models import SUPPORTED_MARKETS
from sources.akshare_source import AKShareSource
from sources.sec import SECSource
from watchlist import as_dicts, read_watchlist


class StructuredSource(Protocol):
    def fetch(self, company) -> dict:
        ...


def build_default_sources() -> dict[str, StructuredSource]:
    akshare_source = AKShareSource()
    return {
        "US": SECSource(),
        "CN": akshare_source,
        "HK": akshare_source,
    }


def _is_valid_symbol(symbol: str, market: str) -> bool:
    if not symbol:
        return False
    if market == "US":
        return bool(re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol))
    if market == "CN":
        return bool(re.fullmatch(r"\d{6}", symbol))
    if market == "HK":
        return bool(re.fullmatch(r"\d{5}", symbol))
    return bool(re.fullmatch(r"[A-Z0-9.-]+", symbol))


def _record_invalid_symbol(db_path: str | Path, company) -> None:
    _record_quality_error(db_path, company, errors.invalid_symbol(company.symbol, company.market))


def _record_unsupported_market(db_path: str | Path, company) -> None:
    _record_quality_error(db_path, company, errors.unsupported_market(company.market))


def _record_quality_error(db_path: str | Path, company, error: errors.AppError) -> None:
    db.insert_quality_issue(
        db_path,
        **error.to_quality_issue(symbol=company.symbol, market=company.market),
    )


def _refresh_company(
    db_path: str | Path,
    company,
    source: StructuredSource,
    fetch_run_id: int,
    *,
    report_period: str | None = None,
    history_scope: str = "recent_5y",
) -> int:
    payload = normalizer.prepare_structured_payload(source.fetch(company))
    payload["fetch_run_id"] = fetch_run_id
    db.insert_raw_payload(db_path, payload)
    facts = normalizer.normalize_structured_payload(payload)
    facts = _filter_facts(facts, report_period=report_period, history_scope=history_scope)
    empty_issues = 0
    if not facts:
        normalizer.record_empty_payload_issue(
            db_path,
            {
                **payload,
                "facts": [],
            },
        )
        empty_issues = 1
    for fact in facts:
        db.insert_financial_fact(db_path, fact)
    return len(facts) - empty_issues


def _filter_facts(
    facts: list[dict],
    *,
    report_period: str | None = None,
    history_scope: str = "recent_5y",
) -> list[dict]:
    if report_period:
        normalized_period, _, _ = normalizer.normalize_report_period(report_period)
        return [fact for fact in facts if fact["report_period"] == normalized_period]
    if history_scope == "latest_quarter":
        quarter_periods = sorted(
            {
                fact["report_period"]
                for fact in facts
                if str(fact.get("fiscal_period", "")).startswith("Q")
            }
        )
        if not quarter_periods:
            return []
        latest_period = quarter_periods[-1]
        return [fact for fact in facts if fact["report_period"] == latest_period]
    if history_scope == "recent_5y":
        fiscal_years = [
            int(fact["fiscal_year"])
            for fact in facts
            if fact.get("fiscal_year") is not None
        ]
        if not fiscal_years:
            return []
        earliest_year = max(fiscal_years) - 4
        return [
            fact
            for fact in facts
            if fact.get("fiscal_year") is not None and int(fact["fiscal_year"]) >= earliest_year
        ]
    return facts


def refresh_from_watchlist(
    db_path: str | Path,
    watchlist_path: str | Path,
    *,
    sources: dict[str, StructuredSource] | None = None,
    report_period: str | None = None,
    history_scope: str = "recent_5y",
) -> dict[str, int]:
    companies = read_watchlist(watchlist_path)
    return refresh_companies(
        db_path,
        companies,
        sources=sources,
        report_period=report_period,
        history_scope=history_scope,
    )


def refresh_companies(
    db_path: str | Path,
    companies: Iterable,
    *,
    sources: dict[str, StructuredSource] | None = None,
    report_period: str | None = None,
    history_scope: str = "recent_5y",
) -> dict[str, int]:
    companies = list(companies)
    db.sync_companies(db_path, companies)
    fetch_run_id = db.create_fetch_run(db_path)
    unsupported = 0
    success_count = 0
    failure_count = 0
    configured_sources = build_default_sources() if sources is None else sources

    for company in companies:
        if not _is_valid_symbol(company.symbol, company.market):
            failure_count += 1
            _record_invalid_symbol(db_path, company)
            continue

        if company.market not in SUPPORTED_MARKETS:
            unsupported += 1
            failure_count += 1
            _record_unsupported_market(db_path, company)
            continue

        source = configured_sources.get(company.market)
        if source is None:
            failure_count += 1
            _record_quality_error(db_path, company, errors.source_not_configured(company.market))
            continue

        try:
            _refresh_company(
                db_path,
                company,
                source,
                fetch_run_id,
                report_period=report_period,
                history_scope=history_scope,
            )
            db.refresh_freshness_from_disclosure_events(
                db_path,
                symbol=company.symbol,
                market=company.market,
            )
        except normalizer.MissingFieldError as exc:
            failure_count += 1
            _record_quality_error(db_path, company, errors.missing_field(exc))
            continue
        except Exception as exc:
            failure_count += 1
            _record_quality_error(db_path, company, errors.source_error(exc))
            continue
        success_count += 1

    validation_summary = validator.run_validation(db_path)
    if failure_count and success_count:
        status = "partial_failed"
    elif failure_count:
        status = "failed"
    else:
        status = "completed"
    db.finish_fetch_run(
        db_path,
        run_id=fetch_run_id,
        status=status,
        success_count=success_count,
        failure_count=failure_count,
    )
    return {
        "companies_loaded": len(as_dicts(companies)),
        "unsupported_markets": unsupported,
        "success_count": success_count,
        "failure_count": failure_count,
        "companies_checked": validation_summary["companies_checked"],
    }
