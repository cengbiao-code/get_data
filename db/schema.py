from __future__ import annotations

from pathlib import Path

from .connection import connect


DEFAULT_VALIDATION_RULES = (
    ("source_required", "Source fields must be present", "source", 1),
    ("fetched_at_required", "Fetched timestamp must be present", "source", 1),
    ("payload_hash_required", "Payload hash must be present", "source", 1),
    (
        "freshness_current_or_marked",
        "Freshness must be current or explicitly marked",
        "freshness",
        1,
    ),
    (
        "three_statements_present",
        "Income statement, balance sheet, and cash flow should exist",
        "completeness",
        1,
    ),
    (
        "key_income_fields_present",
        "Revenue and profit fields should exist",
        "completeness",
        1,
    ),
    (
        "key_balance_fields_present",
        "Assets, liabilities, and equity fields should exist",
        "completeness",
        1,
    ),
    (
        "key_cash_flow_fields_present",
        "Operating cash flow fields should exist",
        "completeness",
        1,
    ),
    (
        "balance_sheet_balances",
        "Assets should equal liabilities plus equity",
        "consistency",
        1,
    ),
    (
        "duplicate_period_detected",
        "Duplicate report periods should be flagged",
        "time_series",
        1,
    ),
    (
        "large_change_detected",
        "Large period changes should be flagged",
        "time_series",
        1,
    ),
    (
        "payload_revision_detected",
        "Payload hash changes should be visible",
        "version",
        1,
    ),
)


def init_db(db_path: str | Path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(
            """
            create table if not exists companies (
                id integer primary key autoincrement,
                symbol text not null,
                market text not null,
                name text not null,
                currency text,
                enabled integer not null default 1,
                notes text not null default '',
                data_status text not null default 'needs_review',
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp,
                unique(symbol, market)
            );

            create table if not exists fetch_runs (
                id integer primary key autoincrement,
                started_at text not null,
                ended_at text,
                status text not null,
                success_count integer not null default 0,
                failure_count integer not null default 0,
                message text
            );

            create table if not exists raw_payloads (
                id integer primary key autoincrement,
                company_id integer,
                source text not null,
                source_url text,
                source_confidence text not null,
                payload_hash text not null,
                payload_json text not null,
                fetched_at text not null,
                fetch_run_id integer,
                foreign key(company_id) references companies(id),
                foreign key(fetch_run_id) references fetch_runs(id)
            );

            create table if not exists financial_facts (
                id integer primary key autoincrement,
                company_id integer not null,
                company_symbol text not null,
                market text not null,
                statement_type text not null,
                report_period text not null,
                fiscal_year integer,
                fiscal_period text,
                line_item text not null,
                raw_line_item text,
                value real,
                unit text,
                currency text,
                source text not null,
                source_url text,
                source_confidence text not null,
                payload_hash text not null,
                fetched_at text not null,
                quality_status text not null default 'needs_review',
                freshness_status text not null default 'unknown',
                validation_status text not null default 'needs_review',
                version integer not null default 1,
                created_at text not null default current_timestamp,
                foreign key(company_id) references companies(id)
            );

            create table if not exists quality_issues (
                id integer primary key autoincrement,
                company_id integer,
                symbol text,
                market text,
                issue_type text not null,
                severity text not null,
                message text not null,
                report_period text,
                created_at text not null,
                resolved_at text,
                foreign key(company_id) references companies(id)
            );

            create table if not exists disclosure_events (
                id integer primary key autoincrement,
                company_id integer,
                symbol text not null,
                market text not null,
                report_period text,
                disclosure_date text,
                disclosure_type text,
                title text,
                url text,
                document_hash text,
                fetched_at text not null,
                foreign key(company_id) references companies(id)
            );

            create table if not exists data_freshness (
                company_id integer primary key,
                latest_structured_period text,
                latest_disclosure_period text,
                latest_disclosure_date text,
                freshness_status text not null,
                checked_at text not null,
                foreign key(company_id) references companies(id)
            );

            create table if not exists validation_rules (
                id integer primary key autoincrement,
                name text not null unique,
                description text not null,
                category text not null,
                enabled integer not null default 1,
                created_at text not null default current_timestamp
            );

            create table if not exists validation_results (
                id integer primary key autoincrement,
                company_id integer,
                rule_name text not null,
                status text not null,
                severity text not null,
                message text not null,
                report_period text,
                checked_at text not null,
                foreign key(company_id) references companies(id)
            );

            create table if not exists data_quality_scores (
                id integer primary key autoincrement,
                company_id integer not null,
                scope text not null,
                report_period text,
                score integer not null,
                quality_status text not null,
                calculated_at text not null,
                foreign key(company_id) references companies(id)
            );

            create table if not exists manual_reviews (
                id integer primary key autoincrement,
                company_id integer,
                target_table text not null,
                target_id integer not null,
                status text not null default 'open',
                reviewer text,
                notes text,
                created_at text not null,
                reviewed_at text,
                foreign key(company_id) references companies(id)
            );

            create table if not exists crawler_sources (
                id integer primary key autoincrement,
                name text not null unique,
                market text not null,
                enabled integer not null default 0,
                compliance_status text not null default 'unknown',
                notes text not null default '',
                checked_at text
            );

            create table if not exists crawler_runs (
                id integer primary key autoincrement,
                started_at text not null,
                ended_at text,
                status text not null,
                source_name text,
                message text
            );

            create table if not exists crawler_documents (
                id integer primary key autoincrement,
                company_id integer,
                symbol text not null,
                market text not null,
                title text not null,
                url text not null,
                document_type text,
                document_hash text not null,
                fetched_at text not null,
                crawler_run_id integer,
                unique(document_hash),
                foreign key(company_id) references companies(id),
                foreign key(crawler_run_id) references crawler_runs(id)
            );

            create table if not exists extracted_candidates (
                id integer primary key autoincrement,
                crawler_document_id integer,
                company_id integer,
                statement_type text,
                report_period text,
                line_item text,
                value real,
                unit text,
                confidence real,
                review_status text not null default 'unverified',
                created_at text not null,
                foreign key(crawler_document_id) references crawler_documents(id),
                foreign key(company_id) references companies(id)
            );

            create index if not exists idx_financial_facts_company_period
                on financial_facts(company_id, report_period, statement_type);
            create index if not exists idx_financial_facts_quality
                on financial_facts(quality_status);
            create index if not exists idx_raw_payloads_hash
                on raw_payloads(payload_hash);
            create index if not exists idx_quality_issues_company
                on quality_issues(company_id, issue_type);
            create index if not exists idx_validation_results_company
                on validation_results(company_id, rule_name);
            """
        )
        conn.executemany(
            """
            insert or ignore into validation_rules(name, description, category, enabled)
            values(?, ?, ?, ?)
            """,
            DEFAULT_VALIDATION_RULES,
        )
        conn.commit()
