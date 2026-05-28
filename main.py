from __future__ import annotations

import argparse
from pathlib import Path

import db
import exporter
import refresher
import validator
from crawler.runner import crawl_disclosures_from_watchlist
from web.app import create_app


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local listed-company financial database"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Create or migrate SQLite schema")
    init_db.add_argument("--db", required=True, help="SQLite database path")

    refresh = subparsers.add_parser("refresh", help="Refresh companies from watchlist")
    refresh.add_argument("--watchlist", required=True, help="CSV watchlist path")
    refresh.add_argument("--db", required=True, help="SQLite database path")

    validate = subparsers.add_parser("validate", help="Run validation rules")
    validate.add_argument("--db", required=True, help="SQLite database path")

    crawl = subparsers.add_parser(
        "crawl-disclosures", help="Collect disclosure metadata only"
    )
    crawl.add_argument("--watchlist", required=True, help="CSV watchlist path")
    crawl.add_argument("--db", required=True, help="SQLite database path")

    configure_crawler = subparsers.add_parser(
        "configure-crawler-source", help="Configure crawler source compliance"
    )
    configure_crawler.add_argument("--db", required=True, help="SQLite database path")
    configure_crawler.add_argument("--name", required=True, help="Crawler source name")
    configure_crawler.add_argument("--market", required=True, help="Market code")
    configure_crawler.add_argument(
        "--compliance-status",
        required=True,
        choices=["unknown", "allowed", "permitted", "blocked"],
        help="Compliance review status",
    )
    configure_crawler.add_argument(
        "--enabled",
        type=_parse_bool,
        default=False,
        help="Whether this source may be used: true or false",
    )
    configure_crawler.add_argument("--notes", default="", help="Compliance notes")

    review = subparsers.add_parser(
        "review-candidates", help="List unverified extracted candidates"
    )
    review.add_argument("--db", required=True, help="SQLite database path")

    export = subparsers.add_parser("export", help="Export trusted facts")
    export.add_argument("--db", required=True, help="SQLite database path")
    export.add_argument("--symbol", help="Optional company symbol")
    export.add_argument("--format", default="csv", help="Comma-separated: csv,jsonl")
    export.add_argument("--out", required=True, help="Output directory")
    export.add_argument(
        "--quality-status",
        help="Optional comma-separated statuses; default trusted,usable",
    )

    serve = subparsers.add_parser("serve", help="Start local Web UI")
    serve.add_argument("--db", required=True, help="SQLite database path")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-db":
        db.init_db(args.db)
        print(f"initialized {args.db}")
        return 0

    if args.command == "refresh":
        db.init_db(args.db)
        summary = refresher.refresh_from_watchlist(args.db, args.watchlist)
        print(summary)
        return 0

    if args.command == "validate":
        db.init_db(args.db)
        summary = validator.run_validation(args.db)
        print(summary)
        return 0

    if args.command == "crawl-disclosures":
        db.init_db(args.db)
        summary = crawl_disclosures_from_watchlist(args.db, args.watchlist)
        print(summary)
        return 0

    if args.command == "configure-crawler-source":
        db.init_db(args.db)
        db.upsert_crawler_source_compliance(
            args.db,
            name=args.name,
            market=args.market,
            compliance_status=args.compliance_status,
            enabled=args.enabled,
            notes=args.notes,
        )
        print(
            {
                "name": args.name,
                "market": args.market,
                "enabled": args.enabled,
                "compliance_status": args.compliance_status,
            }
        )
        return 0

    if args.command == "review-candidates":
        db.init_db(args.db)
        with db.connect(args.db) as conn:
            count = conn.execute(
                "select count(*) from extracted_candidates where review_status = 'unverified'"
            ).fetchone()[0]
        print({"unverified_candidates": count})
        return 0

    if args.command == "export":
        db.init_db(args.db)
        files = exporter.export_facts(
            args.db,
            Path(args.out),
            symbol=args.symbol,
            formats=_split_csv(args.format),
            statuses=_split_csv(args.quality_status) if args.quality_status else None,
        )
        print({key: str(path) for key, path in files.items()})
        return 0

    if args.command == "serve":
        db.init_db(args.db)
        try:
            import uvicorn
        except ModuleNotFoundError as exc:
            raise SystemExit(
                "uvicorn is required for serve. Install dependencies with requirements.txt"
            ) from exc

        uvicorn.run(create_app(args.db), host=args.host, port=args.port)
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
