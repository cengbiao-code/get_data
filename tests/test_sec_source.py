import unittest

from models import WatchlistCompany
from sources.sec import SECSource, SECSourceError


class FakeSECClient:
    def __init__(self, responses):
        self.responses = responses
        self.urls = []

    def get_json(self, url):
        self.urls.append(url)
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


class SECSourceTests(unittest.TestCase):
    def test_resolve_cik_from_company_tickers_payload(self):
        source = SECSource(
            ticker_mapping={
                "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
            }
        )

        cik = source.resolve_cik("aapl")

        self.assertEqual(cik, "0000320193")

    def test_fetch_companyfacts_converts_key_concepts_to_structured_payload(self):
        ticker_url = SECSource.COMPANY_TICKERS_URL
        facts_url = SECSource.companyfacts_url("0000320193")
        client = FakeSECClient(
            {
                ticker_url: {
                    "0": {
                        "cik_str": 320193,
                        "ticker": "AAPL",
                        "title": "Apple Inc.",
                    }
                },
                facts_url: {
                    "facts": {
                        "us-gaap": {
                            "Revenues": {
                                "units": {
                                    "USD": [
                                        {
                                            "fy": 2025,
                                            "fp": "Q4",
                                            "end": "2025-09-30",
                                            "val": 100,
                                            "form": "10-K",
                                        }
                                    ]
                                }
                            },
                            "Assets": {
                                "units": {
                                    "USD": [
                                        {
                                            "fy": 2025,
                                            "fp": "Q4",
                                            "end": "2025-09-30",
                                            "val": 300,
                                            "form": "10-K",
                                        }
                                    ]
                                }
                            },
                            "NetCashProvidedByUsedInOperatingActivities": {
                                "units": {
                                    "USD": [
                                        {
                                            "fy": 2025,
                                            "fp": "Q4",
                                            "end": "2025-09-30",
                                            "val": 40,
                                            "form": "10-K",
                                        }
                                    ]
                                }
                            },
                            "CostOfRevenue": {
                                "units": {
                                    "USD": [
                                        {
                                            "fy": 2025,
                                            "fp": "Q4",
                                            "end": "2025-09-30",
                                            "val": 60,
                                            "form": "10-K",
                                        }
                                    ]
                                }
                            },
                            "ResearchAndDevelopmentExpense": {
                                "units": {
                                    "USD": [
                                        {
                                            "fy": 2025,
                                            "fp": "Q4",
                                            "end": "2025-09-30",
                                            "val": 15,
                                            "form": "10-K",
                                        }
                                    ]
                                }
                            },
                            "CashAndCashEquivalentsAtCarryingValue": {
                                "units": {
                                    "USD": [
                                        {
                                            "fy": 2025,
                                            "fp": "Q4",
                                            "end": "2025-09-30",
                                            "val": 20,
                                            "form": "10-K",
                                        }
                                    ]
                                }
                            },
                            "PaymentsToAcquirePropertyPlantAndEquipment": {
                                "units": {
                                    "USD": [
                                        {
                                            "fy": 2025,
                                            "fp": "Q4",
                                            "end": "2025-09-30",
                                            "val": 5,
                                            "form": "10-K",
                                        }
                                    ]
                                }
                            },
                        }
                    }
                },
            }
        )
        source = SECSource(client=client, fetched_at="2026-01-01T00:00:00Z")

        payload = source.fetch(WatchlistCompany("AAPL", "US", "Apple Inc.", True))

        self.assertEqual(payload["company_symbol"], "AAPL")
        self.assertEqual(payload["market"], "US")
        self.assertEqual(payload["source"], "SEC CompanyFacts")
        self.assertEqual(payload["source_confidence"], "official")
        self.assertEqual(payload["source_url"], facts_url)
        self.assertEqual(payload["payload"]["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0]["val"], 100)
        facts = {(fact["statement_type"], fact["line_item"]) for fact in payload["facts"]}
        self.assertIn(("income_statement", "revenue"), facts)
        self.assertIn(("income_statement", "cost_of_revenue"), facts)
        self.assertIn(("income_statement", "research_and_development"), facts)
        self.assertIn(("balance_sheet", "total_assets"), facts)
        self.assertIn(("balance_sheet", "cash_and_cash_equivalents"), facts)
        self.assertIn(("cash_flow", "operating_cash_flow"), facts)
        self.assertIn(("cash_flow", "capital_expenditure"), facts)

    def test_missing_symbol_raises_sec_source_error(self):
        source = SECSource(ticker_mapping={})

        with self.assertRaises(SECSourceError):
            source.resolve_cik("NOPE")

    def test_client_failure_raises_sec_source_error(self):
        source = SECSource(client=FakeSECClient({SECSource.COMPANY_TICKERS_URL: RuntimeError("network down")}))

        with self.assertRaises(SECSourceError):
            source.resolve_cik("AAPL")
