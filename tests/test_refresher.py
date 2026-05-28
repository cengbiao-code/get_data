import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import db
import refresher
from models import WatchlistCompany


class FakeSource:
    def __init__(self, payloads):
        self.payloads = payloads

    def fetch(self, company):
        payload = self.payloads[company.symbol]
        return {
            "company_symbol": company.symbol,
            "market": company.market,
            "company_name": payload.get("company_name"),
            "source": payload["source"],
            "source_url": payload.get("source_url"),
            "source_confidence": payload["source_confidence"],
            "fetched_at": "2026-01-01T00:00:00Z",
            "facts": payload["facts"],
        }


class FailingSource:
    def fetch(self, company):
        raise RuntimeError(f"boom for {company.symbol}")


class RefresherTests(unittest.TestCase):
    def write_watchlist(self, tmp, content):
        path = Path(tmp) / "watchlist.csv"
        path.write_text(content, encoding="utf-8")
        return path

    def test_refresh_with_mock_sources_saves_raw_facts_run_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            watchlist = self.write_watchlist(
                tmp,
                "symbol,market,name,enabled,notes\n"
                "AAPL,US,Apple Inc.,true,\n"
                "600519,CN,Kweichow Moutai,true,\n",
            )
            db.init_db(db_path)

            summary = refresher.refresh_from_watchlist(
                db_path,
                watchlist,
                sources={
                    "US": FakeSource(
                        {
                            "AAPL": {
                                "source": "SEC CompanyFacts",
                                "source_confidence": "official",
                                "facts": [
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2025Q4",
                                        "line_item": "revenue",
                                        "value": 100,
                                    }
                                ],
                            }
                        }
                    ),
                    "CN": FakeSource(
                        {
                            "600519": {
                                "source": "AKShare",
                                "source_confidence": "structured_open_source",
                                "facts": [
                                    {
                                        "statement_type": "cash_flow",
                                        "report_period": "2025Q4",
                                        "line_item": "operating_cash_flow",
                                        "value": 30,
                                    }
                                ],
                            }
                        }
                    ),
                },
            )

            with closing(db.connect(db_path)) as conn:
                run = conn.execute("select * from fetch_runs").fetchone()
                raw_count = conn.execute("select count(*) from raw_payloads").fetchone()[0]
                fact_count = conn.execute(
                    "select count(*) from financial_facts"
                ).fetchone()[0]
                validation_count = conn.execute(
                    "select count(*) from validation_results"
                ).fetchone()[0]

            self.assertEqual(summary["success_count"], 2)
            self.assertEqual(summary["failure_count"], 0)
            self.assertEqual(run["status"], "completed")
            self.assertEqual(raw_count, 2)
            self.assertEqual(fact_count, 2)
            self.assertGreater(validation_count, 0)

    def test_refresh_companies_accepts_direct_company_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)

            summary = refresher.refresh_companies(
                db_path,
                [WatchlistCompany("AAPL", "US", "AAPL", True)],
                sources={
                    "US": FakeSource(
                        {
                            "AAPL": {
                                "source": "SEC CompanyFacts",
                                "company_name": "Apple Inc.",
                                "source_confidence": "official",
                                "facts": [
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2025Q4",
                                        "line_item": "revenue",
                                        "value": 100,
                                    }
                                ],
                            }
                        }
                    )
                },
            )

            with closing(db.connect(db_path)) as conn:
                company_count = conn.execute("select count(*) from companies").fetchone()[0]
                company_name = conn.execute(
                    "select name from companies where symbol = 'AAPL'"
                ).fetchone()["name"]
                fact_count = conn.execute("select count(*) from financial_facts").fetchone()[0]

            self.assertEqual(summary["success_count"], 1)
            self.assertEqual(company_count, 1)
            self.assertEqual(company_name, "Apple Inc.")
            self.assertEqual(fact_count, 1)

    def test_refresh_companies_can_filter_to_specific_report_period(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)

            summary = refresher.refresh_companies(
                db_path,
                [WatchlistCompany("AAPL", "US", "Apple Inc.", True)],
                sources={
                    "US": FakeSource(
                        {
                            "AAPL": {
                                "source": "SEC CompanyFacts",
                                "source_confidence": "official",
                                "facts": [
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2024Q4",
                                        "line_item": "revenue",
                                        "value": 80,
                                    },
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2025Q4",
                                        "line_item": "revenue",
                                        "value": 100,
                                    },
                                ],
                            }
                        }
                    )
                },
                report_period="2025Q4",
            )

            with closing(db.connect(db_path)) as conn:
                periods = [
                    row["report_period"]
                    for row in conn.execute("select distinct report_period from financial_facts")
                ]

            self.assertEqual(summary["success_count"], 1)
            self.assertEqual(periods, ["2025Q4"])

    def test_refresh_updates_data_freshness_from_saved_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)

            refresher.refresh_companies(
                db_path,
                [WatchlistCompany("600519", "CN", "Kweichow Moutai", True)],
                sources={
                    "CN": FakeSource(
                        {
                            "600519": {
                                "source": "AKShare",
                                "source_confidence": "structured_open_source",
                                "facts": [
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2025Q3",
                                        "line_item": "revenue",
                                        "value": 80,
                                    },
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2025Q4",
                                        "line_item": "revenue",
                                        "value": 100,
                                    },
                                ],
                            }
                        }
                    )
                },
            )

            with closing(db.connect(db_path)) as conn:
                row = conn.execute(
                    """
                    select latest_structured_period, latest_disclosure_period,
                           freshness_status
                    from data_freshness
                    """
                ).fetchone()

            self.assertEqual(row["latest_structured_period"], "2025Q4")
            self.assertIsNone(row["latest_disclosure_period"])
            self.assertEqual(row["freshness_status"], "unknown")

    def test_refresh_companies_can_collect_latest_quarter_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)

            refresher.refresh_companies(
                db_path,
                [WatchlistCompany("AAPL", "US", "Apple Inc.", True)],
                sources={
                    "US": FakeSource(
                        {
                            "AAPL": {
                                "source": "SEC CompanyFacts",
                                "source_confidence": "official",
                                "facts": [
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2025Q3",
                                        "line_item": "revenue",
                                        "value": 80,
                                    },
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2025Q4",
                                        "line_item": "revenue",
                                        "value": 100,
                                    },
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2025FY",
                                        "line_item": "revenue",
                                        "value": 300,
                                    },
                                ],
                            }
                        }
                    )
                },
                history_scope="latest_quarter",
            )

            with closing(db.connect(db_path)) as conn:
                periods = [
                    row["report_period"]
                    for row in conn.execute("select distinct report_period from financial_facts")
                ]

            self.assertEqual(periods, ["2025Q4"])

    def test_refresh_companies_defaults_to_recent_five_years(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)

            refresher.refresh_companies(
                db_path,
                [WatchlistCompany("AAPL", "US", "Apple Inc.", True)],
                sources={
                    "US": FakeSource(
                        {
                            "AAPL": {
                                "source": "SEC CompanyFacts",
                                "source_confidence": "official",
                                "facts": [
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2020Q4",
                                        "line_item": "revenue",
                                        "value": 50,
                                    },
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2021Q4",
                                        "line_item": "revenue",
                                        "value": 60,
                                    },
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2025Q4",
                                        "line_item": "revenue",
                                        "value": 100,
                                    },
                                ],
                            }
                        }
                    )
                },
            )

            with closing(db.connect(db_path)) as conn:
                periods = [
                    row["report_period"]
                    for row in conn.execute(
                        "select distinct report_period from financial_facts order by report_period"
                    )
                ]

            self.assertEqual(periods, ["2021Q4", "2025Q4"])

    def test_refresh_companies_can_still_collect_all_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)

            refresher.refresh_companies(
                db_path,
                [WatchlistCompany("AAPL", "US", "Apple Inc.", True)],
                sources={
                    "US": FakeSource(
                        {
                            "AAPL": {
                                "source": "SEC CompanyFacts",
                                "source_confidence": "official",
                                "facts": [
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2020Q4",
                                        "line_item": "revenue",
                                        "value": 50,
                                    },
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2025Q4",
                                        "line_item": "revenue",
                                        "value": 100,
                                    },
                                ],
                            }
                        }
                    )
                },
                history_scope="all",
            )

            with closing(db.connect(db_path)) as conn:
                periods = [
                    row["report_period"]
                    for row in conn.execute(
                        "select distinct report_period from financial_facts order by report_period"
                    )
                ]

            self.assertEqual(periods, ["2020Q4", "2025Q4"])

    def test_refresh_defaults_to_real_structured_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            watchlist = self.write_watchlist(
                tmp,
                "symbol,market,name,enabled,notes\n"
                "AAPL,US,Apple Inc.,true,\n"
                "600519,CN,Kweichow Moutai,true,\n"
                "00700,HK,Tencent Holdings,true,\n",
            )
            db.init_db(db_path)

            us_source = FakeSource(
                {
                    "AAPL": {
                        "source": "SEC CompanyFacts",
                        "source_confidence": "official",
                        "facts": [
                            {
                                "statement_type": "income_statement",
                                "report_period": "2025Q4",
                                "line_item": "revenue",
                                "value": 100,
                            }
                        ],
                    }
                }
            )
            akshare_source = FakeSource(
                {
                    "600519": {
                        "source": "AKShare",
                        "source_confidence": "structured_open_source",
                        "facts": [
                            {
                                "statement_type": "balance_sheet",
                                "report_period": "2025Q4",
                                "line_item": "total_assets",
                                "value": 200,
                            }
                        ],
                    },
                    "00700": {
                        "source": "AKShare",
                        "source_confidence": "structured_open_source",
                        "facts": [
                            {
                                "statement_type": "cash_flow",
                                "report_period": "2025Q4",
                                "line_item": "operating_cash_flow",
                                "value": 30,
                            }
                        ],
                    },
                }
            )

            with patch("refresher.SECSource", return_value=us_source) as sec_cls, patch(
                "refresher.AKShareSource", return_value=akshare_source
            ) as akshare_cls:
                summary = refresher.refresh_from_watchlist(db_path, watchlist)

            with closing(db.connect(db_path)) as conn:
                source_names = {
                    row["source"]
                    for row in conn.execute("select distinct source from raw_payloads")
                }

            sec_cls.assert_called_once_with()
            akshare_cls.assert_called_once_with()
            self.assertEqual(summary["success_count"], 3)
            self.assertEqual(summary["failure_count"], 0)
            self.assertEqual(source_names, {"SEC CompanyFacts", "AKShare"})

    def test_explicit_empty_sources_keeps_source_not_configured_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            watchlist = self.write_watchlist(
                tmp,
                "symbol,market,name,enabled,notes\n"
                "AAPL,US,Apple Inc.,true,\n",
            )
            db.init_db(db_path)

            summary = refresher.refresh_from_watchlist(db_path, watchlist, sources={})

            with closing(db.connect(db_path)) as conn:
                issue_count = conn.execute(
                    "select count(*) from quality_issues where issue_type = 'source_not_configured'"
                ).fetchone()[0]

            self.assertEqual(summary["success_count"], 0)
            self.assertEqual(summary["failure_count"], 1)
            self.assertEqual(issue_count, 1)

    def test_refresh_records_source_failure_and_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            watchlist = self.write_watchlist(
                tmp,
                "symbol,market,name,enabled,notes\n"
                "AAPL,US,Apple Inc.,true,\n"
                "600519,CN,Kweichow Moutai,true,\n",
            )
            db.init_db(db_path)

            summary = refresher.refresh_from_watchlist(
                db_path,
                watchlist,
                sources={
                    "US": FailingSource(),
                    "CN": FakeSource(
                        {
                            "600519": {
                                "source": "AKShare",
                                "source_confidence": "structured_open_source",
                                "facts": [
                                    {
                                        "statement_type": "income_statement",
                                        "report_period": "2025Q4",
                                        "line_item": "revenue",
                                        "value": 20,
                                    }
                                ],
                            }
                        }
                    ),
                },
            )

            with closing(db.connect(db_path)) as conn:
                run = conn.execute("select * from fetch_runs").fetchone()
                failure_issues = conn.execute(
                    "select count(*) from quality_issues where issue_type = 'source_error'"
                ).fetchone()[0]
                fact_count = conn.execute(
                    "select count(*) from financial_facts where company_symbol = '600519'"
                ).fetchone()[0]

            self.assertEqual(summary["success_count"], 1)
            self.assertEqual(summary["failure_count"], 1)
            self.assertEqual(run["status"], "partial_failed")
            self.assertEqual(failure_issues, 1)
            self.assertEqual(fact_count, 1)

    def test_refresh_records_unsupported_market(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            watchlist = self.write_watchlist(
                tmp,
                "symbol,market,name,enabled,notes\n"
                "7203,JP,Toyota,true,\n",
            )
            db.init_db(db_path)

            summary = refresher.refresh_from_watchlist(db_path, watchlist, sources={})

            with closing(db.connect(db_path)) as conn:
                issue_count = conn.execute(
                    "select count(*) from quality_issues where issue_type = 'unsupported_market'"
                ).fetchone()[0]

            self.assertEqual(summary["unsupported_markets"], 1)
            self.assertEqual(summary["failure_count"], 1)
            self.assertEqual(issue_count, 1)
