from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .connection import connect, utc_now


def sync_companies(db_path: str | Path, companies: Iterable[Any]) -> None:
    now = utc_now()
    rows = []
    for company in companies:
        if hasattr(company, "symbol"):
            rows.append(
                (
                    company.symbol,
                    company.market,
                    company.name,
                    1 if company.enabled else 0,
                    company.notes,
                    now,
                )
            )
        else:
            rows.append(
                (
                    company["symbol"],
                    company["market"],
                    company["name"],
                    1 if company.get("enabled", True) else 0,
                    company.get("notes", ""),
                    now,
                )
            )

    with connect(db_path) as conn:
        conn.executemany(
            """
            insert into companies(symbol, market, name, enabled, notes, updated_at)
            values(?, ?, ?, ?, ?, ?)
            on conflict(symbol, market) do update set
                name = excluded.name,
                enabled = excluded.enabled,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            rows,
        )
        conn.commit()


def get_company_id(conn: sqlite3.Connection, symbol: str, market: str) -> int:
    row = conn.execute(
        "select id from companies where symbol = ? and market = ?",
        (symbol, market),
    ).fetchone()
    if row is None:
        raise ValueError(f"company not found: {symbol}.{market}")
    return int(row["id"])
