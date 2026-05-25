from __future__ import annotations

import db
from crawler.base import BaseDisclosureCrawler, CrawlerRequestPolicy
from crawler.document_store import save_crawler_document


class CninfoClient:
    def fetch_announcements(self, symbol: str):
        raise NotImplementedError("CninfoClient requires a concrete implementation")

    def fetch_content(self, url: str) -> bytes:
        raise NotImplementedError("CninfoClient requires a concrete implementation")


class CninfoCrawler(BaseDisclosureCrawler):
    source_name = "cninfo"

    def __init__(
        self,
        enabled: bool = False,
        *,
        client: CninfoClient | None = None,
        request_policy: CrawlerRequestPolicy | None = None,
    ) -> None:
        super().__init__(enabled=enabled, request_policy=request_policy)
        self.client = client or CninfoClient()

    def collect(self, db_path, *, symbol: str, market: str = "CN") -> int:
        self.ensure_enabled()
        run_id = db.create_crawler_run(db_path, source_name=self.source_name)
        try:
            announcements = self.fetch_with_policy(
                f"{self.source_name}:announcements:{symbol}",
                lambda: self.client.fetch_announcements(symbol),
            )
            saved_count = 0
            for announcement in announcements:
                content = self._announcement_content(announcement)
                save_crawler_document(
                    db_path,
                    symbol=symbol,
                    market=market,
                    title=announcement["title"],
                    url=announcement["url"],
                    document_type=announcement.get("document_type", "announcement"),
                    content=content,
                    report_period=announcement.get("report_period"),
                    disclosure_date=announcement.get("disclosure_date"),
                    crawler_run_id=run_id,
                )
                saved_count += 1
            db.refresh_freshness_from_disclosure_events(
                db_path,
                symbol=symbol,
                market=market,
            )
            db.finish_crawler_run(
                db_path,
                run_id=run_id,
                status="completed",
                message=f"Collected {saved_count} disclosure metadata records",
            )
            return saved_count
        except Exception as exc:
            db.finish_crawler_run(
                db_path,
                run_id=run_id,
                status="failed",
                message=str(exc),
            )
            raise

    def _announcement_content(self, announcement) -> bytes:
        if "content" in announcement:
            return self._to_bytes(announcement["content"])
        return self._to_bytes(
            self.fetch_with_policy(
                f"{self.source_name}:document:{announcement['url']}",
                lambda: self.client.fetch_content(announcement["url"]),
            )
        )

    @staticmethod
    def _to_bytes(content) -> bytes:
        if isinstance(content, bytes):
            return content
        return str(content).encode("utf-8")
