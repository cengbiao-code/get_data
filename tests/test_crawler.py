import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import db
from crawler.base import (
    BaseDisclosureCrawler,
    CrawlerRequestPolicy,
    record_compliance_check,
    record_disabled_source,
)
from crawler.cninfo import CninfoCrawler
from crawler.document_store import save_crawler_document, save_extracted_candidate
from crawler.runner import crawl_disclosures_from_watchlist


class CrawlerLayerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "financial.sqlite3"
        db.init_db(self.db_path)
        db.sync_companies(
            self.db_path,
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

    def tearDown(self):
        self.tmp.cleanup()

    def test_disabled_crawler_records_crawler_disabled(self):
        record_disabled_source(
            self.db_path,
            symbol="600519",
            market="CN",
            source_name="cninfo",
        )

        with closing(db.connect(self.db_path)) as conn:
            issue_count = conn.execute(
                "select count(*) from quality_issues where issue_type = 'crawler_disabled'"
            ).fetchone()[0]
            run = conn.execute("select status, source_name from crawler_runs").fetchone()

        self.assertEqual(issue_count, 1)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["source_name"], "cninfo")

    def test_crawler_compliance_check_is_recorded(self):
        record_compliance_check(
            self.db_path,
            source_name="cninfo",
            market="CN",
            compliance_status="allowed",
            notes="robots checked; public disclosure pages only",
        )

        with closing(db.connect(self.db_path)) as conn:
            source = conn.execute(
                """
                select name, market, compliance_status, notes, checked_at
                from crawler_sources
                where name = 'cninfo'
                """
            ).fetchone()

        self.assertEqual(source["name"], "cninfo")
        self.assertEqual(source["market"], "CN")
        self.assertEqual(source["compliance_status"], "allowed")
        self.assertIn("robots checked", source["notes"])
        self.assertIsNotNone(source["checked_at"])

    def test_crawler_request_policy_caches_and_rate_limits(self):
        now = [0.0]
        sleeps = []

        def clock():
            return now[0]

        def sleep(seconds):
            sleeps.append(seconds)
            now[0] += seconds

        crawler = BaseDisclosureCrawler(
            enabled=True,
            request_policy=CrawlerRequestPolicy(
                min_interval_seconds=2.0,
                max_retries=0,
                clock=clock,
                sleep=sleep,
            ),
        )
        calls = {"count": 0}

        def fetcher():
            calls["count"] += 1
            return {"ok": calls["count"]}

        first = crawler.fetch_with_policy("same-key", fetcher)
        cached = crawler.fetch_with_policy("same-key", fetcher)
        second = crawler.fetch_with_policy("other-key", fetcher)

        self.assertEqual(first, {"ok": 1})
        self.assertEqual(cached, {"ok": 1})
        self.assertEqual(second, {"ok": 2})
        self.assertEqual(calls["count"], 2)
        self.assertEqual(sleeps, [2.0])

    def test_crawler_request_policy_stops_after_retry_limit(self):
        crawler = BaseDisclosureCrawler(
            enabled=True,
            request_policy=CrawlerRequestPolicy(min_interval_seconds=0, max_retries=2),
        )
        attempts = {"count": 0}

        def fetcher():
            attempts["count"] += 1
            raise RuntimeError("temporary failure")

        with self.assertRaises(RuntimeError):
            crawler.fetch_with_policy("unstable", fetcher)

        self.assertEqual(attempts["count"], 3)

    def test_duplicate_disclosure_documents_are_deduped_by_hash(self):
        first_id = save_crawler_document(
            self.db_path,
            symbol="600519",
            market="CN",
            title="2025 Annual Report",
            url="https://example.test/report.pdf",
            document_type="annual_report",
            content=b"same-pdf-bytes",
            report_period="2025Q4",
            disclosure_date="2026-04-30",
        )
        second_id = save_crawler_document(
            self.db_path,
            symbol="600519",
            market="CN",
            title="2025 Annual Report duplicate",
            url="https://example.test/report-copy.pdf",
            document_type="annual_report",
            content=b"same-pdf-bytes",
            report_period="2025Q4",
            disclosure_date="2026-04-30",
        )

        with closing(db.connect(self.db_path)) as conn:
            document_count = conn.execute(
                "select count(*) from crawler_documents"
            ).fetchone()[0]
            disclosure_count = conn.execute(
                "select count(*) from disclosure_events"
            ).fetchone()[0]
            fact_count = conn.execute("select count(*) from financial_facts").fetchone()[0]

        self.assertEqual(first_id, second_id)
        self.assertEqual(document_count, 1)
        self.assertEqual(disclosure_count, 1)
        self.assertEqual(fact_count, 0)

    def test_unverified_candidate_does_not_enter_financial_facts(self):
        document_id = save_crawler_document(
            self.db_path,
            symbol="600519",
            market="CN",
            title="2025 Annual Report",
            url="https://example.test/report.pdf",
            document_type="annual_report",
            content=b"candidate-source",
            report_period="2025Q4",
            disclosure_date="2026-04-30",
        )

        save_extracted_candidate(
            self.db_path,
            crawler_document_id=document_id,
            symbol="600519",
            market="CN",
            statement_type="income_statement",
            report_period="2025Q4",
            line_item="revenue",
            value=100.0,
            unit="CNY",
            confidence=0.65,
        )

        with closing(db.connect(self.db_path)) as conn:
            candidate = conn.execute(
                "select review_status, value from extracted_candidates"
            ).fetchone()
            fact_count = conn.execute("select count(*) from financial_facts").fetchone()[0]

        self.assertEqual(candidate["review_status"], "unverified")
        self.assertEqual(candidate["value"], 100.0)
        self.assertEqual(fact_count, 0)

    def test_cninfo_crawler_collects_cn_disclosure_metadata_only(self):
        class FakeCninfoClient:
            def fetch_announcements(self, symbol):
                self.symbol = symbol
                return [
                    {
                        "title": "贵州茅台2025年年度报告",
                        "url": "https://static.cninfo.test/600519/annual.pdf",
                        "document_type": "annual_report",
                        "report_period": "2025Q4",
                        "disclosure_date": "2026-04-30",
                    }
                ]

            def fetch_content(self, url):
                self.url = url
                return b"cn annual report bytes"

        client = FakeCninfoClient()
        crawler = CninfoCrawler(
            enabled=True,
            client=client,
            request_policy=CrawlerRequestPolicy(min_interval_seconds=0),
        )

        saved_count = crawler.collect(self.db_path, symbol="600519", market="CN")

        with closing(db.connect(self.db_path)) as conn:
            document = conn.execute(
                """
                select symbol, market, title, url, document_type, document_hash
                from crawler_documents
                """
            ).fetchone()
            event = conn.execute(
                """
                select report_period, disclosure_date, disclosure_type, title, url,
                       document_hash
                from disclosure_events
                """
            ).fetchone()
            run = conn.execute(
                "select source_name, status, message from crawler_runs"
            ).fetchone()
            fact_count = conn.execute("select count(*) from financial_facts").fetchone()[0]

        self.assertEqual(saved_count, 1)
        self.assertEqual(client.symbol, "600519")
        self.assertEqual(client.url, "https://static.cninfo.test/600519/annual.pdf")
        self.assertEqual(document["symbol"], "600519")
        self.assertEqual(document["market"], "CN")
        self.assertEqual(document["document_type"], "annual_report")
        self.assertEqual(event["report_period"], "2025Q4")
        self.assertEqual(event["disclosure_date"], "2026-04-30")
        self.assertEqual(event["disclosure_type"], "annual_report")
        self.assertEqual(event["title"], document["title"])
        self.assertEqual(event["url"], document["url"])
        self.assertEqual(event["document_hash"], document["document_hash"])
        self.assertEqual(run["source_name"], "cninfo")
        self.assertEqual(run["status"], "completed")
        self.assertIn("1 disclosure", run["message"])
        self.assertEqual(fact_count, 0)

    def test_crawl_disclosures_from_watchlist_runs_allowed_cn_crawler(self):
        watchlist_path = Path(self.tmp.name) / "watchlist.csv"
        watchlist_path.write_text(
            "symbol,market,name,enabled,notes\n"
            "600519,CN,贵州茅台,true,\n"
            "AAPL,US,Apple Inc.,true,\n",
            encoding="utf-8",
        )
        db.upsert_crawler_source_compliance(
            self.db_path,
            name="cninfo",
            market="CN",
            compliance_status="allowed",
            enabled=True,
        )

        class FakeCrawler:
            source_name = "cninfo"

            def __init__(self):
                self.calls = []

            def collect(self, db_path, *, symbol, market):
                self.calls.append((str(db_path), symbol, market))
                return 2

        fake_crawler = FakeCrawler()

        summary = crawl_disclosures_from_watchlist(
            self.db_path,
            watchlist_path,
            crawler_factory=lambda _company: fake_crawler,
        )

        with closing(db.connect(self.db_path)) as conn:
            company_count = conn.execute("select count(*) from companies").fetchone()[0]

        self.assertEqual(fake_crawler.calls, [(str(self.db_path), "600519", "CN")])
        self.assertEqual(company_count, 2)
        self.assertEqual(
            summary,
            {
                "companies_loaded": 2,
                "success_count": 1,
                "failure_count": 0,
                "skipped_count": 1,
                "documents_saved": 2,
            },
        )
