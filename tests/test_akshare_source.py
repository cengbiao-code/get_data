import unittest

import pandas as pd

from models import WatchlistCompany
from sources.akshare_source import AKShareSource, AKShareSourceError


class FakeAKShareClient:
    def __init__(self, frames):
        self.frames = frames
        self.calls = []

    def fetch_statement(self, symbol, market, statement_type):
        self.calls.append((symbol, market, statement_type))
        value = self.frames[(market, statement_type)]
        if isinstance(value, Exception):
            raise value
        return value


class AKShareSourceTests(unittest.TestCase):
    def test_fetch_cn_three_statements_converts_dataframes_to_payload(self):
        client = FakeAKShareClient(
            {
                ("CN", "income_statement"): pd.DataFrame(
                    [
                        {
                            "report_period": "2025-12-31",
                            "line_item": "revenue",
                            "raw_line_item": "营业收入",
                            "value": 100,
                            "currency": "CNY",
                        }
                    ]
                ),
                ("CN", "balance_sheet"): pd.DataFrame(
                    [
                        {
                            "report_period": "2025-12-31",
                            "line_item": "total_assets",
                            "raw_line_item": "资产总计",
                            "value": 300,
                            "currency": "CNY",
                        }
                    ]
                ),
                ("CN", "cash_flow"): pd.DataFrame(
                    [
                        {
                            "report_period": "2025-12-31",
                            "line_item": "operating_cash_flow",
                            "raw_line_item": "经营活动现金流量净额",
                            "value": 20,
                            "currency": "CNY",
                        }
                    ]
                ),
            }
        )
        source = AKShareSource(client=client, fetched_at="2026-01-01T00:00:00Z")

        payload = source.fetch(WatchlistCompany("600519", "CN", "Kweichow Moutai", True))

        self.assertEqual(payload["source"], "AKShare")
        self.assertEqual(payload["source_confidence"], "structured_open_source")
        self.assertEqual(payload["company_symbol"], "600519")
        self.assertEqual(payload["market"], "CN")
        self.assertEqual(len(payload["facts"]), 3)
        self.assertIn(("600519", "CN", "income_statement"), client.calls)
        self.assertIn(
            ("balance_sheet", "total_assets"),
            {(fact["statement_type"], fact["line_item"]) for fact in payload["facts"]},
        )

    def test_fetch_hk_three_statements_converts_dataframes_to_payload(self):
        client = FakeAKShareClient(
            {
                ("HK", "income_statement"): pd.DataFrame(
                    [{"report_period": "2025FY", "line_item": "revenue", "value": 50}]
                ),
                ("HK", "balance_sheet"): pd.DataFrame(
                    [
                        {
                            "report_period": "2025FY",
                            "line_item": "total_liabilities",
                            "value": 10,
                        }
                    ]
                ),
                ("HK", "cash_flow"): pd.DataFrame(
                    [
                        {
                            "report_period": "2025FY",
                            "line_item": "operating_cash_flow",
                            "value": 5,
                        }
                    ]
                ),
            }
        )
        source = AKShareSource(client=client, fetched_at="2026-01-01T00:00:00Z")

        payload = source.fetch(WatchlistCompany("00700", "HK", "Tencent", True))

        self.assertEqual(payload["market"], "HK")
        self.assertEqual(len(payload["facts"]), 3)
        self.assertIn(("00700", "HK", "cash_flow"), client.calls)

    def test_empty_dataframes_return_empty_payload(self):
        client = FakeAKShareClient(
            {
                ("CN", "income_statement"): pd.DataFrame(),
                ("CN", "balance_sheet"): pd.DataFrame(),
                ("CN", "cash_flow"): pd.DataFrame(),
            }
        )
        source = AKShareSource(client=client, fetched_at="2026-01-01T00:00:00Z")

        payload = source.fetch(WatchlistCompany("600519", "CN", "Kweichow Moutai", True))

        self.assertEqual(payload["facts"], [])
        self.assertEqual(len(payload["payload"]["statements"]), 3)

    def test_client_failure_raises_akshare_source_error(self):
        client = FakeAKShareClient(
            {
                ("CN", "income_statement"): RuntimeError("akshare changed"),
                ("CN", "balance_sheet"): pd.DataFrame(),
                ("CN", "cash_flow"): pd.DataFrame(),
            }
        )
        source = AKShareSource(client=client, fetched_at="2026-01-01T00:00:00Z")

        with self.assertRaises(AKShareSourceError):
            source.fetch(WatchlistCompany("600519", "CN", "Kweichow Moutai", True))

