import tempfile
import unittest
from pathlib import Path

import db
from web.app import create_app


def web_get(app, path):
    return app.state.http_get(path)


def web_post(app, path):
    return app.state.http_post(path)


class FakeSource:
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
                    "line_item": "revenue",
                    "value": 100,
                    "quality_status": "trusted",
                }
            ],
        }


class WebAppTests(unittest.TestCase):
    def test_create_app_exposes_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)
            app = create_app(db_path)

        paths = {route.path for route in app.routes}
        self.assertIn("/", paths)
        self.assertIn("/companies", paths)
        self.assertIn("/validation-issues", paths)
        self.assertIn("/companies/{symbol}", paths)
        self.assertIn("/search", paths)
        self.assertIn("/collect", paths)
        self.assertIn("/runs", paths)
        self.assertIn("/export", paths)
        self.assertIn("/validate", paths)

    def test_dashboard_stats_are_available_without_http_client(self):
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
            app = create_app(db_path)
            stats = app.state.dashboard_provider()

            self.assertEqual(stats["company_count"], 1)
            self.assertIn("trusted", stats["quality_counts"])

    def test_core_pages_return_200(self):
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
            app = create_app(db_path)

            for path in ("/", "/companies", "/validation-issues"):
                response = web_get(app, path)
                self.assertEqual(response.status_code, 200, path)

            dashboard = web_get(app, "/")
            companies = web_get(app, "/companies")
            self.assertIn('action="/search"', dashboard.text)
            self.assertIn('action="/collect"', dashboard.text)
            self.assertIn('name="report_period"', dashboard.text)
            self.assertIn('name="history_scope"', dashboard.text)
            self.assertIn('value="recent_5y" selected', dashboard.text)
            self.assertIn("近5年财报", dashboard.text)
            self.assertIn('name="symbol"', dashboard.text)
            self.assertNotIn('action="/collect"', companies.text)
            self.assertIn("本地财务数据库", dashboard.text)
            self.assertIn("本地财务工作台", dashboard.text)
            self.assertIn("采集公司数据", dashboard.text)
            self.assertNotIn("<details", dashboard.text)
            self.assertNotIn('href="/runs"', dashboard.text)
            self.assertIn('href="/companies/AAPL"', dashboard.text)

    def test_company_detail_runs_and_export_pages_return_200(self):
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
            run_id = db.create_fetch_run(db_path)
            db.finish_fetch_run(
                db_path,
                run_id=run_id,
                status="completed",
                success_count=1,
                failure_count=0,
            )
            db.insert_financial_fact(
                db_path,
                {
                    "company_symbol": "AAPL",
                    "market": "US",
                    "statement_type": "income_statement",
                    "report_period": "2025Q4",
                    "line_item": "revenue",
                    "value": 100,
                    "source": "SEC CompanyFacts",
                    "source_confidence": "official",
                    "payload_hash": "hash",
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "quality_status": "trusted",
                },
            )
            app = create_app(db_path)

            detail = web_get(app, "/companies/AAPL")
            runs = web_get(app, "/runs")
            export = web_get(app, "/export")

            self.assertEqual(detail.status_code, 200)
            self.assertIn("AAPL", detail.text)
            self.assertIn("期间覆盖", detail.text)
            self.assertIn("2025Q4", detail.text)
            self.assertIn("利润表", detail.text)
            self.assertEqual(runs.status_code, 200)
            self.assertIn("完成", runs.text)
            self.assertEqual(export.status_code, 200)
            self.assertIn("导出", export.text)

    def test_stock_code_search_returns_financial_report_detail(self):
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
            db.insert_financial_fact(
                db_path,
                {
                    "company_symbol": "AAPL",
                    "market": "US",
                    "statement_type": "income_statement",
                    "report_period": "2025Q4",
                    "line_item": "revenue",
                    "value": 100,
                    "source": "SEC CompanyFacts",
                    "source_confidence": "official",
                    "payload_hash": "hash",
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "quality_status": "trusted",
                },
            )
            app = create_app(db_path)

            response = web_get(app, "/search?symbol=aapl")

            self.assertEqual(response.status_code, 200)
            self.assertIn("AAPL", response.text)
            self.assertIn("期间覆盖", response.text)
            self.assertIn("2025Q4", response.text)
            self.assertIn("利润表", response.text)

    def test_stock_code_search_can_filter_by_report_period(self):
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
            for period, value in (("2024Q4", 80), ("2025Q4", 100)):
                db.insert_financial_fact(
                    db_path,
                    {
                        "company_symbol": "AAPL",
                        "market": "US",
                        "statement_type": "income_statement",
                        "report_period": period,
                        "line_item": "revenue",
                        "value": value,
                        "source": "SEC CompanyFacts",
                        "source_confidence": "official",
                        "payload_hash": f"hash-{period}",
                        "fetched_at": "2026-01-01T00:00:00Z",
                        "quality_status": "trusted",
                    },
                )
            app = create_app(db_path)

            response = web_get(app, "/search?symbol=AAPL&report_period=2025Q4")

            self.assertEqual(response.status_code, 200)
            self.assertIn("2025Q4", response.text)
            self.assertIn("100.0", response.text)
            self.assertNotIn("2024Q4", response.text)

    def test_stock_code_search_reports_missing_company(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)
            app = create_app(db_path)

            response = web_get(app, "/search?symbol=NOPE")

            self.assertEqual(response.status_code, 404)
            self.assertIn("未找到公司", response.text)
            self.assertIn("请先刷新数据", response.text)

    def test_collect_by_stock_code_refreshes_company_and_shows_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)
            app = create_app(db_path, refresh_sources={"US": FakeSource()})

            response = web_get(
                app,
                "/collect?query=AAPL&market=US&name=Apple%20Inc.&history_scope=all",
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn("采集完成", response.text)
            self.assertIn("AAPL", response.text)
            self.assertIn("期间覆盖", response.text)
            self.assertIn("2025Q4", response.text)

    def test_collect_can_filter_to_requested_report_period(self):
        class MultiPeriodSource:
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

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)
            app = create_app(db_path, refresh_sources={"US": MultiPeriodSource()})

            response = web_get(
                app,
                "/collect?query=AAPL&market=US&name=Apple%20Inc.&history_scope=period&report_period=2025Q4",
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn("2025Q4", response.text)
            self.assertNotIn("2024Q4", response.text)

    def test_companies_page_shows_collected_and_missing_periods(self):
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
            db.insert_financial_fact(
                db_path,
                {
                    "company_symbol": "AAPL",
                    "market": "US",
                    "statement_type": "income_statement",
                    "report_period": "2025Q4",
                    "line_item": "revenue",
                    "value": 100,
                    "source": "SEC CompanyFacts",
                    "source_confidence": "official",
                    "payload_hash": "hash",
                    "fetched_at": "2026-01-01T00:00:00Z",
                    "quality_status": "trusted",
                },
            )
            app = create_app(db_path)

            response = web_get(app, "/companies")

            self.assertEqual(response.status_code, 200)
            self.assertIn("已采集期间", response.text)
            self.assertIn("2025Q4", response.text)
            self.assertIn("缺失报表", response.text)
            self.assertIn("资产负债表", response.text)
            self.assertIn("现金流量表", response.text)

    def test_collect_by_existing_company_name_refreshes_matched_company(self):
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
            app = create_app(db_path, refresh_sources={"US": FakeSource()})

            response = web_get(app, "/collect?query=Apple%20Inc.&market=auto")

            self.assertEqual(response.status_code, 200)
            self.assertIn("采集完成", response.text)
            self.assertIn("AAPL", response.text)

    def test_collect_unknown_name_asks_for_symbol_and_market(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "financial.sqlite3"
            db.init_db(db_path)
            app = create_app(db_path, refresh_sources={"US": FakeSource()})

            response = web_get(app, "/collect?query=苹果公司&market=auto")

            self.assertEqual(response.status_code, 400)
            self.assertIn("无法仅凭公司名称采集", response.text)
            self.assertIn("股票代码", response.text)

    def test_manual_validate_endpoint_runs_validation(self):
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
            app = create_app(db_path)

            response = web_post(app, "/validate")

            self.assertEqual(response.status_code, 200)
            self.assertIn("companies_checked", response.text)
