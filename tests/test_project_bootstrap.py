import csv
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import db
import exporter
import main
import validator
from watchlist import read_watchlist


class ProjectBootstrapTests(unittest.TestCase):
    def test_cli_help_runs(self):
        result = subprocess.run(
            [sys.executable, "main.py", "--help"],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("init-db", result.stdout)
        self.assertIn("refresh", result.stdout)
        self.assertIn("validate", result.stdout)
        self.assertIn("crawl-disclosures", result.stdout)
        self.assertIn("review-candidates", result.stdout)
        self.assertIn("export", result.stdout)
        self.assertIn("serve", result.stdout)

    def test_core_modules_import(self):
        self.assertTrue(callable(main.build_parser))
        self.assertTrue(callable(db.init_db))
        self.assertTrue(callable(validator.run_validation))
        self.assertTrue(callable(exporter.export_facts))

    def test_validate_command_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            result = subprocess.run(
                [sys.executable, "main.py", "validate", "--db", str(db_path)],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("companies_checked", result.stdout)

    def test_crawl_disclosures_command_outputs_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            watchlist_path = Path(tmp) / "watchlist.csv"
            watchlist_path.write_text(
                "symbol,market,name,enabled,notes\n"
                "600519,CN,贵州茅台,true,\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "main.py",
                    "crawl-disclosures",
                    "--watchlist",
                    str(watchlist_path),
                    "--db",
                    str(db_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("companies_loaded", result.stdout)
        self.assertNotIn("scaffolded", result.stdout)

    def test_watchlist_example_has_required_fields(self):
        path = Path(__file__).resolve().parents[1] / "watchlist.example.csv"

        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(
                reader.fieldnames,
                ["symbol", "market", "name", "enabled", "notes"],
            )


class DatabaseInitTests(unittest.TestCase):
    def test_init_db_creates_core_tables_rules_and_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)

            with closing(sqlite3.connect(db_path)) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "select name from sqlite_master where type = 'table'"
                    )
                }
                indexes = {
                    row[0]
                    for row in conn.execute(
                        "select name from sqlite_master where type = 'index'"
                    )
                }
                rule_count = conn.execute(
                    "select count(*) from validation_rules"
                ).fetchone()[0]

            self.assertTrue(
                {
                    "companies",
                    "fetch_runs",
                    "financial_facts",
                    "raw_payloads",
                    "quality_issues",
                    "disclosure_events",
                    "data_freshness",
                    "validation_rules",
                    "validation_results",
                    "data_quality_scores",
                    "manual_reviews",
                    "crawler_sources",
                    "crawler_runs",
                    "crawler_documents",
                    "extracted_candidates",
                }.issubset(tables)
            )
            self.assertIn("idx_financial_facts_company_period", indexes)
            self.assertGreaterEqual(rule_count, 12)

    def test_init_db_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)
            with closing(sqlite3.connect(db_path)) as conn:
                conn.execute(
                    """
                    insert into companies(symbol, market, name, enabled)
                    values('AAPL', 'US', 'Apple Inc.', 1)
                    """
                )
                conn.commit()

            db.init_db(db_path)

            with closing(sqlite3.connect(db_path)) as conn:
                count = conn.execute(
                    "select count(*) from companies where symbol = 'AAPL'"
                ).fetchone()[0]
            self.assertEqual(count, 1)


class WatchlistTests(unittest.TestCase):
    def test_read_watchlist_skips_disabled_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "watchlist.csv"
            path.write_text(
                "symbol,market,name,enabled,notes\n"
                "AAPL,US,Apple Inc.,true,\n"
                "MSFT,US,Microsoft,false,\n",
                encoding="utf-8",
            )

            companies = read_watchlist(path)

        self.assertEqual([company.symbol for company in companies], ["AAPL"])

    def test_read_watchlist_requires_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("symbol,market,name\nAAPL,US,Apple Inc.\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                read_watchlist(path)


class ExportAndValidationTests(unittest.TestCase):
    def test_validate_writes_results_and_quality_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)
            db.sync_companies(
                db_path,
                [
                    {
                        "symbol": "AAPL",
                        "market": "US",
                        "name": "Apple Inc.",
                        "enabled": True,
                        "notes": "",
                    }
                ],
            )

            summary = validator.run_validation(db_path)

            self.assertEqual(summary["companies_checked"], 1)
            with closing(sqlite3.connect(db_path)) as conn:
                result_count = conn.execute(
                    "select count(*) from validation_results"
                ).fetchone()[0]
                score_count = conn.execute(
                    "select count(*) from data_quality_scores"
                ).fetchone()[0]
            self.assertGreater(result_count, 0)
            self.assertEqual(score_count, 1)

    def test_export_defaults_to_trusted_and_usable(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            out_dir = Path(tmp) / "out"
            db.init_db(db_path)
            db.sync_companies(
                db_path,
                [
                    {
                        "symbol": "AAPL",
                        "market": "US",
                        "name": "Apple Inc.",
                        "enabled": True,
                        "notes": "",
                    }
                ],
            )
            db.insert_financial_fact(
                db_path,
                {
                    "company_symbol": "AAPL",
                    "market": "US",
                    "statement_type": "income_statement",
                    "report_period": "2025Q4",
                    "fiscal_year": 2025,
                    "fiscal_period": "Q4",
                    "line_item": "revenue",
                    "raw_line_item": "Revenue",
                    "value": 100,
                    "unit": "USD",
                    "currency": "USD",
                    "source": "SEC CompanyFacts",
                    "source_url": "https://data.sec.gov/",
                    "source_confidence": "official",
                    "payload_hash": "hash-trusted",
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "quality_status": "trusted",
                },
            )
            db.insert_financial_fact(
                db_path,
                {
                    "company_symbol": "AAPL",
                    "market": "US",
                    "statement_type": "income_statement",
                    "report_period": "2025Q3",
                    "fiscal_year": 2025,
                    "fiscal_period": "Q3",
                    "line_item": "revenue",
                    "raw_line_item": "Revenue",
                    "value": 80,
                    "unit": "USD",
                    "currency": "USD",
                    "source": "SEC CompanyFacts",
                    "source_url": "https://data.sec.gov/",
                    "source_confidence": "official",
                    "payload_hash": "hash-stale",
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "quality_status": "stale",
                },
            )

            files = exporter.export_facts(
                db_path,
                out_dir,
                symbol="AAPL",
                formats=["csv", "jsonl"],
            )

            csv_text = files["csv"].read_text(encoding="utf-8")
            jsonl_text = files["jsonl"].read_text(encoding="utf-8")
            self.assertIn("hash-trusted", csv_text)
            self.assertNotIn("hash-stale", csv_text)
            self.assertIn('"quality_status": "trusted"', jsonl_text)
            self.assertNotIn('"quality_status": "stale"', jsonl_text)
