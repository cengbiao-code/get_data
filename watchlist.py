from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from models import WatchlistCompany


REQUIRED_FIELDS = ["symbol", "market", "name", "enabled", "notes"]
TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def _is_enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in TRUE_VALUES


def read_watchlist(path: str | Path) -> list[WatchlistCompany]:
    watchlist_path = Path(path)
    with watchlist_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != REQUIRED_FIELDS:
            raise ValueError(
                "watchlist must contain fields: " + ", ".join(REQUIRED_FIELDS)
            )

        companies = []
        for row in reader:
            if not _is_enabled(row.get("enabled")):
                continue
            companies.append(
                WatchlistCompany(
                    symbol=(row.get("symbol") or "").strip().upper(),
                    market=(row.get("market") or "").strip().upper(),
                    name=(row.get("name") or "").strip(),
                    enabled=True,
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return companies


def as_dicts(companies: Iterable[WatchlistCompany]) -> list[dict[str, object]]:
    return [
        {
            "symbol": company.symbol,
            "market": company.market,
            "name": company.name,
            "enabled": company.enabled,
            "notes": company.notes,
        }
        for company in companies
    ]

