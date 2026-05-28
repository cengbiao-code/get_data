import importlib.util
import os
import unittest

import normalizer
from models import WatchlistCompany
from sources.akshare_source import AKShareSource
from sources.sec import SECSource


try:
    import pytest

    pytestmark = pytest.mark.integration
except ModuleNotFoundError:
    pytestmark = None


RUN_INTEGRATION = os.environ.get("RUN_INTEGRATION") == "1"


@unittest.skipUnless(RUN_INTEGRATION, "set RUN_INTEGRATION=1 to run real source tests")
class RealSECSourceIntegrationTests(unittest.TestCase):
    def test_real_sec_aapl_companyfacts_payload_normalizes(self):
        payload = SECSource().fetch(WatchlistCompany("AAPL", "US", "Apple Inc.", True))
        facts = normalizer.normalize_structured_payload(payload)

        self.assertEqual(payload["source_confidence"], "official")
        self.assertIn("CIK0000320193", payload["source_url"])
        self.assertGreater(len(facts), 0)
        self.assertTrue(
            any(
                fact["statement_type"] == "balance_sheet"
                and fact["line_item"] == "total_assets"
                for fact in facts
            )
        )


@unittest.skipUnless(RUN_INTEGRATION, "set RUN_INTEGRATION=1 to run real source tests")
@unittest.skipUnless(
    importlib.util.find_spec("akshare") is not None,
    "akshare is not installed",
)
class RealAKShareSourceIntegrationTests(unittest.TestCase):
    def test_real_akshare_cn_payload_normalizes(self):
        payload = AKShareSource().fetch(
            WatchlistCompany("600519", "CN", "Kweichow Moutai", True)
        )
        facts = normalizer.normalize_structured_payload(payload)

        self.assertEqual(payload["source_confidence"], "structured_open_source")
        self.assertEqual(payload["market"], "CN")
        self.assertGreater(len(facts), 0)

    def test_real_akshare_hk_payload_normalizes(self):
        payload = AKShareSource().fetch(
            WatchlistCompany("00700", "HK", "Tencent Holdings", True)
        )
        facts = normalizer.normalize_structured_payload(payload)

        self.assertEqual(payload["source_confidence"], "structured_open_source")
        self.assertEqual(payload["market"], "HK")
        self.assertGreater(len(facts), 0)

