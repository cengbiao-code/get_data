from __future__ import annotations

from pathlib import Path
from typing import Callable

import db
from crawler.base import record_disabled_source
from crawler.cninfo import CninfoCrawler
from models import WatchlistCompany
from watchlist import read_watchlist


CrawlerFactory = Callable[[WatchlistCompany], object]


def crawl_disclosures_from_watchlist(
    db_path: str | Path,
    watchlist_path: str | Path,
    *,
    crawler_factory: CrawlerFactory | None = None,
) -> dict[str, int]:
    companies = read_watchlist(watchlist_path)
    db.sync_companies(db_path, companies)
    return crawl_disclosures_for_companies(
        db_path,
        companies,
        crawler_factory=crawler_factory,
    )


def crawl_disclosures_from_database(
    db_path: str | Path,
    *,
    crawler_factory: CrawlerFactory | None = None,
) -> dict[str, int]:
    companies = _enabled_companies(db_path)
    return crawl_disclosures_for_companies(
        db_path,
        companies,
        crawler_factory=crawler_factory,
    )


def crawl_disclosures_for_companies(
    db_path: str | Path,
    companies: list[WatchlistCompany],
    *,
    crawler_factory: CrawlerFactory | None = None,
) -> dict[str, int]:
    factory = crawler_factory or _default_crawler_factory
    success_count = 0
    failure_count = 0
    skipped_count = 0
    documents_saved = 0

    for company in companies:
        crawler = _crawler_for_company(company, factory)
        if crawler is None:
            skipped_count += 1
            continue
        if not _crawler_source_allowed(db_path, crawler.source_name):
            failure_count += 1
            record_disabled_source(
                db_path,
                symbol=company.symbol,
                market=company.market,
                source_name=crawler.source_name,
            )
            continue
        try:
            documents_saved += int(
                crawler.collect(db_path, symbol=company.symbol, market=company.market)
            )
        except Exception:
            failure_count += 1
            continue
        success_count += 1

    return {
        "companies_loaded": len(companies),
        "success_count": success_count,
        "failure_count": failure_count,
        "skipped_count": skipped_count,
        "documents_saved": documents_saved,
    }


def _enabled_companies(db_path: str | Path) -> list[WatchlistCompany]:
    with db.connect(db_path) as conn:
        rows = conn.execute(
            """
            select symbol, market, name, enabled, notes
            from companies
            where enabled = 1
            order by market, symbol
            """
        ).fetchall()
    return [
        WatchlistCompany(
            row["symbol"],
            row["market"],
            row["name"],
            bool(row["enabled"]),
            row["notes"] or "",
        )
        for row in rows
    ]


def _crawler_for_company(company: WatchlistCompany, factory: CrawlerFactory):
    if company.market != "CN":
        return None
    return factory(company)


def _default_crawler_factory(_company: WatchlistCompany) -> CninfoCrawler:
    return CninfoCrawler(enabled=True)


def _crawler_source_allowed(db_path: str | Path, source_name: str) -> bool:
    with db.connect(db_path) as conn:
        row = conn.execute(
            """
            select enabled, compliance_status
            from crawler_sources
            where name = ?
            """,
            (source_name,),
        ).fetchone()
    return bool(
        row
        and row["enabled"]
        and row["compliance_status"] in {"allowed", "permitted"}
    )
