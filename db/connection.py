from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return False


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(db_path), factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn
