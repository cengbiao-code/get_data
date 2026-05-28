from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_MARKETS = {"US", "CN", "HK"}
QUALITY_STATUSES = ("trusted", "usable", "needs_review", "stale", "failed")
EXPORT_DEFAULT_STATUSES = ("trusted", "usable")
STATEMENT_TYPES = ("income_statement", "balance_sheet", "cash_flow")


@dataclass(frozen=True)
class WatchlistCompany:
    symbol: str
    market: str
    name: str
    enabled: bool
    notes: str = ""

