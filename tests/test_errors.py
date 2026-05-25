import unittest

from errors import AppError, source_error


class ErrorTypeTests(unittest.TestCase):
    def test_app_error_converts_to_quality_issue_payload(self):
        error = AppError(
            issue_type="invalid_symbol",
            severity="high",
            message="Invalid symbol AAPL$ for market US",
            category="input",
            report_period="2025Q4",
        )

        payload = error.to_quality_issue(symbol="AAPL$", market="US")

        self.assertEqual(payload["symbol"], "AAPL$")
        self.assertEqual(payload["market"], "US")
        self.assertEqual(payload["issue_type"], "invalid_symbol")
        self.assertEqual(payload["severity"], "high")
        self.assertEqual(payload["message"], "Invalid symbol AAPL$ for market US")
        self.assertEqual(payload["report_period"], "2025Q4")

    def test_source_error_wraps_exception_as_quality_issue(self):
        error = source_error(RuntimeError("boom"))

        payload = error.to_quality_issue(symbol="AAPL", market="US")

        self.assertEqual(payload["issue_type"], "source_error")
        self.assertEqual(payload["severity"], "high")
        self.assertIn("boom", payload["message"])


if __name__ == "__main__":
    unittest.main()
