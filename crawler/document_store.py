from __future__ import annotations

import hashlib

import db


def document_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def save_crawler_document(
    db_path,
    *,
    symbol: str,
    market: str,
    title: str,
    url: str,
    document_type: str,
    content: bytes,
    report_period: str | None = None,
    disclosure_date: str | None = None,
    crawler_run_id: int | None = None,
) -> int:
    digest = document_hash(content)
    fetched_at = db.utc_now()
    with db.connect(db_path) as conn:
        company_id = db.get_company_id(conn, symbol, market)
        existing = conn.execute(
            "select id from crawler_documents where document_hash = ?",
            (digest,),
        ).fetchone()
        if existing:
            return int(existing["id"])

        cursor = conn.execute(
            """
            insert into crawler_documents(
                company_id, symbol, market, title, url, document_type,
                document_hash, fetched_at, crawler_run_id
            )
            values(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                symbol,
                market,
                title,
                url,
                document_type,
                digest,
                fetched_at,
                crawler_run_id,
            ),
        )
        document_id = int(cursor.lastrowid)
        conn.execute(
            """
            insert into disclosure_events(
                company_id, symbol, market, report_period, disclosure_date,
                disclosure_type, title, url, document_hash, fetched_at
            )
            values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                symbol,
                market,
                report_period,
                disclosure_date,
                document_type,
                title,
                url,
                digest,
                fetched_at,
            ),
        )
        conn.commit()
        return document_id


def save_extracted_candidate(
    db_path,
    *,
    crawler_document_id: int,
    symbol: str,
    market: str,
    statement_type: str,
    report_period: str,
    line_item: str,
    value: float | None,
    unit: str | None,
    confidence: float | None,
) -> int:
    with db.connect(db_path) as conn:
        company_id = db.get_company_id(conn, symbol, market)
        cursor = conn.execute(
            """
            insert into extracted_candidates(
                crawler_document_id, company_id, statement_type, report_period,
                line_item, value, unit, confidence, review_status, created_at
            )
            values(?, ?, ?, ?, ?, ?, ?, ?, 'unverified', ?)
            """,
            (
                crawler_document_id,
                company_id,
                statement_type,
                report_period,
                line_item,
                value,
                unit,
                confidence,
                db.utc_now(),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
