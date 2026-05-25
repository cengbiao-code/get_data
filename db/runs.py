from __future__ import annotations

from pathlib import Path

from .connection import connect, utc_now


def create_fetch_run(db_path: str | Path) -> int:
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            insert into fetch_runs(started_at, status)
            values(?, 'running')
            """,
            (utc_now(),),
        )
        conn.commit()
        return int(cursor.lastrowid)


def finish_fetch_run(
    db_path: str | Path,
    *,
    run_id: int,
    status: str,
    success_count: int,
    failure_count: int,
    message: str | None = None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            update fetch_runs
            set ended_at = ?,
                status = ?,
                success_count = ?,
                failure_count = ?,
                message = ?
            where id = ?
            """,
            (utc_now(), status, success_count, failure_count, message, run_id),
        )
        conn.commit()


def create_crawler_run(db_path: str | Path, *, source_name: str | None = None) -> int:
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            insert into crawler_runs(started_at, status, source_name)
            values(?, 'running', ?)
            """,
            (utc_now(), source_name),
        )
        conn.commit()
        return int(cursor.lastrowid)


def finish_crawler_run(
    db_path: str | Path,
    *,
    run_id: int,
    status: str,
    message: str | None = None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            update crawler_runs
            set ended_at = ?,
                status = ?,
                message = ?
            where id = ?
            """,
            (utc_now(), status, message, run_id),
        )
        conn.commit()


def upsert_crawler_source_compliance(
    db_path: str | Path,
    *,
    name: str,
    market: str,
    compliance_status: str,
    notes: str = "",
    enabled: bool = False,
) -> None:
    checked_at = utc_now()
    with connect(db_path) as conn:
        conn.execute(
            """
            insert into crawler_sources(
                name, market, enabled, compliance_status, notes, checked_at
            )
            values(?, ?, ?, ?, ?, ?)
            on conflict(name) do update set
                market = excluded.market,
                enabled = excluded.enabled,
                compliance_status = excluded.compliance_status,
                notes = excluded.notes,
                checked_at = excluded.checked_at
            """,
            (
                name,
                market,
                1 if enabled else 0,
                compliance_status,
                notes,
                checked_at,
            ),
        )
        conn.commit()
