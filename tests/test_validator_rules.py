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
            fact_status = conn.execute(
                """
                select quality_status, validation_status
                from financial_facts
                where company_symbol = 'AAPL'
                """
            ).fetchone()
        self.assertEqual(status, "needs_review")
        self.assertEqual(fact_status["quality_status"], "needs_review")
        self.assertEqual(fact_status["validation_status"], "needs_review")

    def test_validation_does_not_upgrade_source_quality(self):
        insert_fact(self.db_path, line_item="revenue", value=100)
        insert_fact(self.db_path, line_item="net_income", value=20)
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
            value=60,
        )
        insert_fact(
            self.db_path,
            statement_type="cash_flow",
            line_item="operating_cash_flow",
            value=30,
        )
        with closing(db.connect(self.db_path)) as conn:
            conn.execute(
                """
                update financial_facts
                set quality_status = 'usable', validation_status = 'needs_review'
                where company_symbol = 'AAPL'
                """
            )
            conn.commit()

        validator.run_validation(self.db_path)

        with closing(db.connect(self.db_path)) as conn:
            fact_status = conn.execute(
                """
                select distinct quality_status, validation_status
                from financial_facts
                where company_symbol = 'AAPL'
                """
            ).fetchone()
        self.assertEqual(fact_status["quality_status"], "usable")
        self.assertEqual(fact_status["validation_status"], "trusted")

    def test_validation_can_target_one_company_period(self):
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
            value=120,
        )

        summary = validator.run_validation(
            self.db_path,
            symbol="AAPL",
            report_period="2025Q4",
        )

        with closing(db.connect(self.db_path)) as conn:
            statuses = {
                row["report_period"]: row["quality_status"]
                for row in conn.execute(
                    """
                    select report_period, quality_status
                    from financial_facts
                    where company_symbol = 'AAPL'
                    """
                )
            }
            score = conn.execute(
                """
                select scope, report_period, quality_status
                from data_quality_scores
                """
            ).fetchone()
        self.assertEqual(summary["companies_checked"], 1)
        self.assertEqual(summary["report_period"], "2025Q4")
        self.assertEqual(statuses["2024Q4"], "trusted")
        self.assertEqual(statuses["2025Q4"], "needs_review")
        self.assertEqual(score["scope"], "period")
        self.assertEqual(score["report_period"], "2025Q4")

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
