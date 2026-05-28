import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import db
import normalizer
import pandas as pd
from sources.disclosure_check import compare_structured_and_disclosed_periods
from crawler.document_store import save_crawler_document


class NormalizerTests(unittest.TestCase):
    def test_sec_mock_payload_saves_raw_payload_and_financial_facts(self):
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
            payload = normalizer.prepare_structured_payload(
                {
                    "company_symbol": "AAPL",
                    "market": "US",
                    "source": "SEC CompanyFacts",
                    "source_url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    "source_confidence": "official",
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "facts": [
                        {
                            "statement_type": "income",
                            "report_period": "2025Q4",
                            "fiscal_year": 2025,
                            "fiscal_period": "Q4",
                            "line_item": "revenue",
                            "raw_line_item": "Revenue",
                            "value": 100,
                            "unit": "USD",
                            "currency": "USD",
                            "quality_status": "trusted",
                            "freshness_status": "current",
                            "validation_status": "trusted",
                        }
                    ],
                }
            )

            raw_id = db.insert_raw_payload(db_path, payload)
            facts = normalizer.normalize_structured_payload(payload)
            fact_ids = [db.insert_financial_fact(db_path, fact) for fact in facts]

            with closing(db.connect(db_path)) as conn:
                raw = conn.execute(
                    "select source_confidence, payload_hash, payload_json from raw_payloads where id = ?",
                    (raw_id,),
                ).fetchone()
                fact = conn.execute(
                    """
                    select statement_type, value, source_confidence, payload_hash, version
                    from financial_facts
                    where id = ?
                    """,
                    (fact_ids[0],),
                ).fetchone()

            self.assertEqual(raw["source_confidence"], "official")
            self.assertEqual(raw["payload_hash"], payload["payload_hash"])
            self.assertEqual(json.loads(raw["payload_json"])["facts"][0]["value"], 100)
            self.assertEqual(fact["statement_type"], "income_statement")
            self.assertEqual(fact["value"], 100)
            self.assertEqual(fact["source_confidence"], "official")
            self.assertEqual(fact["payload_hash"], payload["payload_hash"])

    def test_inserting_same_payload_hash_fact_is_idempotent(self):
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
            fact = {
                "company_symbol": "AAPL",
                "market": "US",
                "statement_type": "income_statement",
                "report_period": "2026Q2",
                "fiscal_year": 2026,
                "fiscal_period": "Q2",
                "line_item": "revenue",
                "raw_line_item": "Revenues",
                "value": 100,
                "unit": "USD",
                "currency": "USD",
                "source": "SEC CompanyFacts",
                "source_confidence": "official",
                "payload_hash": "same-hash",
                "fetched_at": "2026-05-01T00:00:00Z",
                "quality_status": "trusted",
            }

            first_id = db.insert_financial_fact(db_path, fact)
            second_id = db.insert_financial_fact(db_path, {**fact, "value": 101})

            with db.connect(db_path) as conn:
                rows = conn.execute(
                    """
                    select id, value, version
                    from financial_facts
                    where company_symbol = 'AAPL'
                    """
                ).fetchall()

            self.assertEqual(first_id, second_id)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["value"], 101)
            self.assertEqual(rows[0]["version"], 1)

    def test_akshare_empty_payload_records_quality_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)
            db.sync_companies(
                db_path,
                [
                    {
                        "symbol": "600519",
                        "market": "CN",
                        "name": "Kweichow Moutai",
                        "enabled": True,
                        "notes": "",
                    }
                ],
            )
            payload = normalizer.prepare_structured_payload(
                {
                    "company_symbol": "600519",
                    "market": "CN",
                    "source": "AKShare",
                    "source_confidence": "structured_open_source",
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "facts": [],
                }
            )

            db.insert_raw_payload(db_path, payload)
            issues = normalizer.record_empty_payload_issue(db_path, payload)

            with closing(db.connect(db_path)) as conn:
                issue_count = conn.execute(
                    "select count(*) from quality_issues where issue_type = 'empty_payload'"
                ).fetchone()[0]

            self.assertEqual(issues, 1)
            self.assertEqual(issue_count, 1)

    def test_akshare_dataframe_can_be_prepared_for_raw_payload(self):
        frame = pd.DataFrame(
            [
                {
                    "statement_type": "balance",
                    "report_period": "2025Q4",
                    "line_item": "total_assets",
                    "raw_line_item": "资产总计",
                    "value": 300,
                    "currency": "CNY",
                }
            ]
        )

        payload = normalizer.prepare_akshare_dataframe_payload(
            frame,
            company_symbol="600519",
            market="CN",
            fetched_at="2026-01-01T00:00:00Z",
        )
        fact = normalizer.normalize_structured_payload(payload)[0]

        self.assertEqual(payload["source"], "AKShare")
        self.assertEqual(payload["source_confidence"], "structured_open_source")
        self.assertEqual(fact["statement_type"], "balance_sheet")
        self.assertEqual(fact["raw_line_item"], "资产总计")

    def test_missing_values_remain_null_not_zero(self):
        payload = normalizer.prepare_structured_payload(
            {
                "company_symbol": "AAPL",
                "market": "US",
                "source": "SEC CompanyFacts",
                "source_confidence": "official",
                "fetched_at": "2026-01-01T00:00:00Z",
                "facts": [
                    {
                        "statement_type": "cashflow",
                        "report_period": "2025Q4",
                        "line_item": "operating_cash_flow",
                        "value": None,
                    }
                ],
            }
        )

        fact = normalizer.normalize_structured_payload(payload)[0]

        self.assertEqual(fact["statement_type"], "cash_flow")
        self.assertIsNone(fact["value"])

    def test_repeated_period_preserves_versions_and_hash_changes(self):
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
            base = {
                "company_symbol": "AAPL",
                "market": "US",
                "source": "SEC CompanyFacts",
                "source_confidence": "official",
                "fetched_at": "2026-01-01T00:00:00Z",
                "facts": [
                    {
                        "statement_type": "income_statement",
                        "report_period": "2025Q4",
                        "line_item": "revenue",
                        "value": 100,
                    }
                ],
            }
            revised = {
                **base,
                "facts": [
                    {
                        "statement_type": "income_statement",
                        "report_period": "2025Q4",
                        "line_item": "revenue",
                        "value": 101,
                    }
                ],
            }

            first = normalizer.prepare_structured_payload(base)
            second = normalizer.prepare_structured_payload(revised)
            db.insert_financial_fact(
                db_path, normalizer.normalize_structured_payload(first)[0]
            )
            db.insert_financial_fact(
                db_path, normalizer.normalize_structured_payload(second)[0]
            )

            with closing(db.connect(db_path)) as conn:
                rows = conn.execute(
                    """
                    select value, payload_hash, version
                    from financial_facts
                    order by version
                    """
                ).fetchall()

            self.assertEqual([row["version"] for row in rows], [1, 2])
            self.assertNotEqual(rows[0]["payload_hash"], rows[1]["payload_hash"])
            self.assertEqual(rows[1]["value"], 101)


class FreshnessTests(unittest.TestCase):
    def test_freshness_status_current_pending_and_stale(self):
        self.assertEqual(
            compare_structured_and_disclosed_periods("2025Q4", "2025Q4"),
            "current",
        )
        self.assertEqual(
            compare_structured_and_disclosed_periods(None, "2025Q4"),
            "pending_structured_data",
        )
        self.assertEqual(
            compare_structured_and_disclosed_periods("2025Q3", "2025Q4"),
            "stale",
        )

    def test_data_freshness_upsert_records_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)
            db.sync_companies(
                db_path,
                [
                    {
                        "symbol": "600519",
                        "market": "CN",
                        "name": "Kweichow Moutai",
                        "enabled": True,
                        "notes": "",
                    }
                ],
            )

            db.upsert_data_freshness(
                db_path,
                symbol="600519",
                market="CN",
                latest_structured_period="2025Q3",
                latest_disclosure_period="2025Q4",
                latest_disclosure_date="2026-04-30",
            )

            with closing(db.connect(db_path)) as conn:
                row = conn.execute(
                    "select freshness_status from data_freshness"
                ).fetchone()
                issue_count = conn.execute(
                    "select count(*) from quality_issues where issue_type = 'pending_structured_data'"
                ).fetchone()[0]

            self.assertEqual(row["freshness_status"], "stale")
            self.assertEqual(issue_count, 1)

    def test_refresh_freshness_detects_akshare_lag_from_disclosures(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)
            db.sync_companies(
                db_path,
                [
                    {
                        "symbol": "600519",
                        "market": "CN",
                        "name": "Kweichow Moutai",
                        "enabled": True,
                        "notes": "",
                    }
                ],
            )
            db.insert_financial_fact(
                db_path,
                {
                    "company_symbol": "600519",
                    "market": "CN",
                    "statement_type": "income_statement",
                    "report_period": "2025Q3",
                    "line_item": "revenue",
                    "value": 100,
                    "source": "AKShare",
                    "source_confidence": "structured_open_source",
                    "payload_hash": "akshare-2025q3",
                    "fetched_at": "2026-01-01T00:00:00Z",
                },
            )
            save_crawler_document(
                db_path,
                symbol="600519",
                market="CN",
                title="贵州茅台2025年年度报告",
                url="https://static.cninfo.test/600519/annual.pdf",
                document_type="annual_report",
                content=b"annual-report",
                report_period="2025Q4",
                disclosure_date="2026-04-30",
            )

            status = db.refresh_freshness_from_disclosure_events(
                db_path,
                symbol="600519",
                market="CN",
            )

            with closing(db.connect(db_path)) as conn:
                row = conn.execute(
                    """
                    select latest_structured_period, latest_disclosure_period,
                           latest_disclosure_date, freshness_status
                    from data_freshness
                    """
                ).fetchone()
                issue = conn.execute(
                    """
                    select issue_type, report_period
                    from quality_issues
                    where issue_type = 'pending_structured_data'
                    """
                ).fetchone()

            self.assertEqual(status, "stale")
            self.assertEqual(row["latest_structured_period"], "2025Q3")
            self.assertEqual(row["latest_disclosure_period"], "2025Q4")
            self.assertEqual(row["latest_disclosure_date"], "2026-04-30")
            self.assertEqual(row["freshness_status"], "stale")
            self.assertEqual(issue["report_period"], "2025Q4")
