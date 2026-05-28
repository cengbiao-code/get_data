from __future__ import annotations


VALID_SEVERITIES = {"low", "medium", "high", "critical"}


class AppError(RuntimeError):
    def __init__(
        self,
        *,
        issue_type: str,
        severity: str,
        message: str,
        category: str,
        report_period: str | None = None,
    ) -> None:
        if not issue_type:
            raise ValueError("issue_type is required")
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"unsupported severity: {severity}")
        super().__init__(message)
        self.issue_type = issue_type
        self.severity = severity
        self.message = message
        self.category = category
        self.report_period = report_period

    def to_quality_issue(self, *, symbol: str, market: str) -> dict[str, str | None]:
        return {
            "symbol": symbol,
            "market": market,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "message": self.message,
            "report_period": self.report_period,
        }


def invalid_symbol(symbol: str, market: str) -> AppError:
    return AppError(
        issue_type="invalid_symbol",
        severity="high",
        category="input",
        message=f"Invalid symbol {symbol} for market {market}",
    )


def unsupported_market(market: str) -> AppError:
    return AppError(
        issue_type="unsupported_market",
        severity="high",
        category="input",
        message=f"Market {market} is not supported",
    )


def source_not_configured(market: str) -> AppError:
    return AppError(
        issue_type="source_not_configured",
        severity="medium",
        category="configuration",
        message=f"No structured source configured for {market}",
    )


def missing_field(exc: Exception) -> AppError:
    return AppError(
        issue_type="missing_field",
        severity="high",
        category="normalization",
        message=str(exc),
    )


def source_error(exc: Exception) -> AppError:
    return AppError(
        issue_type="source_error",
        severity="high",
        category="source",
        message=str(exc),
    )
