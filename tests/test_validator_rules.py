import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import db
import validator


def insert_fact(
    db_path: Path,
    *,
    line_item: str,
    value: float | None,
    statement_type: str = "income_statement",
    report_period: str = "2025Q4",
    payload_hash: str = "hash",
) -> None:
    db.insert_financial_fact(
        db_path,
        {
            "company_symbol": "AAPL",
            "market": "US",
            "statement_type": statement_type,
            "report_period": report_period,
            "fiscal_year": int(report_period[:4]),
            "fiscal_period": report_period[4:],
            "line_item": line_item,
            "raw_line_item": line_item,
            "value": value,
            "unit": "USD",
            "currency": "USD",
            "source": "SEC CompanyFacts",
            "source_url": "https://data.sec.gov/",
            "source_confidence": "official",
            "payload_hash": payload_hash,
            "fetched_at": "2026-01-01T00:00:00Z",
            "quality_status": "trusted",
            "freshness_status": "current",
            "validation_status": "trusted",
        },
    )


class ValidatorRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "financial.sqlite3"
        db.init_db(self.db_path)
        db.sync_companies(
            self.db_path,
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

    def tearDown(self):
        self.tmp.cleanup()

    def rule_names(self) -> list[str]:
        with closing(db.connect(self.db_path)) as conn:
            return [
                row["rule_name"]
                for row in conn.execute(
                    "select rule_name from validation_results order by rule_name"
                )
            ]

    def test_key_income_fields_missing_flags_needs_review(self):
        insert_fact(self.db_path, line_item="revenue", value=100)

        validator.run_validation(self.db_path)

        self.assertIn("key_income_fields_present", self.rule_names())
        with closing(db.connect(self.db_path)) as conn:
            status = conn.execute(
                "select data_status from companies where symbol = 'AAPL'"
            ).fetchone()["data_status"]
        self.assertEqual(status, "needs_review")

    def test_balance_sheet_imbalance_flags_consistency_issue(self):
        insert_fact(
            self.db_path,
            statement_type="balance_sheet",
            line_item="total_assets",
            value=100,
        )
        insert_fact(
            self.db_path,
            statement_type="balance_sheet",
            line_item="total_liabilities",
            value=40,
        )
        insert_fact(
            self.db_path,
            statement_type="balance_sheet",
            line_item="total_equity",
            value=50,
        )

        validator.run_validation(self.db_path)

        self.assertIn("balance_sheet_balances", self.rule_names())

    def test_large_change_detected_flags_time_series_issue(self):
        insert_fact(
            self.db_path,
            report_period="2024Q4",
            line_item="revenue",
            value=100,
        )
        insert_fact(
            self.db_path,
            report_period="2025Q4",
            line_item="revenue",
            value=1200,
        )

        validator.run_validation(self.db_path)

        self.assertIn("large_change_detected", self.rule_names())

    def test_payload_revision_detected_for_changed_hash_same_fact(self):
        insert_fact(
            self.db_path,
            report_period="2025Q4",
            line_item="revenue",
            value=100,
            payload_hash="hash-before",
        )
        insert_fact(
            self.db_path,
            report_period="2025Q4",
            line_item="revenue",
            value=101,
            payload_hash="hash-after",
        )

        validator.run_validation(self.db_path)

        names = self.rule_names()
        self.assertIn("duplicate_period_detected", names)
        self.assertIn("payload_revision_detected", names)

