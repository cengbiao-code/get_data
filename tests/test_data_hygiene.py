import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import db
import normalizer
import refresher


class BadFieldSource:
    def fetch(self, company):
        return {
            "company_symbol": company.symbol,
            "market": company.market,
            "source": "SEC CompanyFacts",
            "source_confidence": "official",
            "fetched_at": "2026-01-01T00:00:00Z",
            "facts": [
                {
                    "statement_type": "income_statement",
                    "report_period": "2025Q4",
                    "value": 100,
                }
            ],
        }


class DataHygieneTests(unittest.TestCase):
    def test_report_period_is_normalized_and_fiscal_fields_are_derived(self):
        payload = normalizer.prepare_structured_payload(
            {
                "company_symbol": "AAPL",
                "market": "US",
                "source": "SEC CompanyFacts",
                "source_confidence": "official",
                "fetched_at": "2026-01-01T00:00:00Z",
                "facts": [
                    {
                        "statement_type": "income_statement",
                        "report_period": "2025-09-30",
                        "line_item": "revenue",
                        "value": 100,
                    }
                ],
            }
        )

        fact = normalizer.normalize_structured_payload(payload)[0]

        self.assertEqual(fact["report_period"], "2025Q3")
        self.assertEqual(fact["fiscal_year"], 2025)
        self.assertEqual(fact["fiscal_period"], "Q3")

    def test_latest_structured_period_uses_newest_fact_not_old_fact(self):
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
            for period in ("2024Q4", "2025Q4"):
                db.insert_financial_fact(
                    db_path,
                    {
                        "company_symbol": "AAPL",
                        "market": "US",
                        "statement_type": "income_statement",
                        "report_period": period,
                        "line_item": "revenue",
                        "value": 100,
                        "source": "SEC CompanyFacts",
                        "source_confidence": "official",
                        "payload_hash": f"hash-{period}",
                        "fetched_at": "2026-01-01T00:00:00Z",
                    },
                )

            status = db.refresh_freshness_from_facts(
                db_path,
                symbol="AAPL",
                market="US",
                latest_disclosure_period="2025Q4",
            )

            with closing(db.connect(db_path)) as conn:
                row = conn.execute(
                    """
                    select latest_structured_period, freshness_status
                    from data_freshness
                    """
                ).fetchone()

            self.assertEqual(status, "current")
            self.assertEqual(row["latest_structured_period"], "2025Q4")
            self.assertEqual(row["freshness_status"], "current")

    def test_refresh_records_invalid_symbol(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            watchlist = Path(tmp) / "watchlist.csv"
            watchlist.write_text(
                "symbol,market,name,enabled,notes\n"
                "AAPL$,US,Bad Apple,true,\n",
                encoding="utf-8",
            )
            db.init_db(db_path)

            summary = refresher.refresh_from_watchlist(db_path, watchlist, sources={})

            with closing(db.connect(db_path)) as conn:
                issue_count = conn.execute(
                    "select count(*) from quality_issues where issue_type = 'invalid_symbol'"
                ).fetchone()[0]

            self.assertEqual(summary["failure_count"], 1)
            self.assertEqual(issue_count, 1)

    def test_refresh_records_missing_field_for_bad_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            watchlist = Path(tmp) / "watchlist.csv"
            watchlist.write_text(
                "symbol,market,name,enabled,notes\n"
                "AAPL,US,Apple Inc.,true,\n",
                encoding="utf-8",
            )
            db.init_db(db_path)

            summary = refresher.refresh_from_watchlist(
                db_path,
                watchlist,
                sources={"US": BadFieldSource()},
            )

            with closing(db.connect(db_path)) as conn:
                issue_count = conn.execute(
                    "select count(*) from quality_issues where issue_type = 'missing_field'"
                ).fetchone()[0]

            self.assertEqual(summary["failure_count"], 1)
            self.assertEqual(issue_count, 1)

