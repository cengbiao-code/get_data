from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time


class CrawlerDisabledError(RuntimeError):
    pass


@dataclass
class CrawlerRequestPolicy:
    min_interval_seconds: float = 1.0
    max_retries: int = 2
    cache_enabled: bool = True
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        if self.min_interval_seconds < 0:
            raise ValueError("min_interval_seconds cannot be negative")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")


class BaseDisclosureCrawler:
    source_name = "base"

    def __init__(
        self,
        enabled: bool = False,
        request_policy: CrawlerRequestPolicy | None = None,
    ) -> None:
        self.enabled = enabled
        self.request_policy = request_policy or CrawlerRequestPolicy()
        self._request_cache = {}
        self._last_request_at: float | None = None

    def collect(self, *_args, **_kwargs):
        self.ensure_enabled()
        raise NotImplementedError

    def ensure_enabled(self) -> None:
        if not self.enabled:
            raise CrawlerDisabledError("crawler source is disabled")

    def fetch_with_policy(self, cache_key: str, fetcher: Callable[[], object]):
        if self.request_policy.cache_enabled and cache_key in self._request_cache:
            return self._request_cache[cache_key]

        attempts = 0
        while True:
            self._wait_for_rate_limit()
            try:
                result = fetcher()
            except Exception:
                if attempts >= self.request_policy.max_retries:
                    raise
                attempts += 1
                continue
            if self.request_policy.cache_enabled:
                self._request_cache[cache_key] = result
            return result

    def _wait_for_rate_limit(self) -> None:
        now = self.request_policy.clock()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            wait_seconds = self.request_policy.min_interval_seconds - elapsed
            if wait_seconds > 0:
                self.request_policy.sleep(wait_seconds)
                now = self.request_policy.clock()
        self._last_request_at = now


def record_compliance_check(
    db_path,
    *,
    source_name: str,
    market: str,
    compliance_status: str,
    notes: str = "",
    enabled: bool = False,
) -> None:
    import db

    db.upsert_crawler_source_compliance(
        db_path,
        name=source_name,
        market=market,
        compliance_status=compliance_status,
        notes=notes,
        enabled=enabled,
    )


def record_disabled_source(db_path, *, symbol: str, market: str, source_name: str) -> None:
    import db

    run_id = db.create_crawler_run(db_path, source_name=source_name)
    db.insert_quality_issue(
        db_path,
        symbol=symbol,
        market=market,
        issue_type="crawler_disabled",
        severity="medium",
        message=f"Crawler source {source_name} is disabled",
    )
    db.finish_crawler_run(
        db_path,
        run_id=run_id,
        status="failed",
        message=f"Crawler source {source_name} is disabled",
    )
