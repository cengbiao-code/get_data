from __future__ import annotations

from datetime import date
import re

import db
from crawler.base import BaseDisclosureCrawler, CrawlerRequestPolicy
from crawler.document_store import save_crawler_document


class CninfoClient:
    def fetch_announcements(self, symbol: str):
        raise NotImplementedError("CninfoClient requires a concrete implementation")

    def fetch_content(self, url: str) -> bytes:
        raise NotImplementedError("CninfoClient requires a concrete implementation")


class AkshareCninfoClient(CninfoClient):
    REPORT_CATEGORIES = ("年报", "半年报", "一季报", "三季报")

    def __init__(
        self,
        *,
        report_func=None,
        today=None,
        start_date: str = "19900101",
    ) -> None:
        self.report_func = report_func
        self.today = today or (lambda: date.today().strftime("%Y%m%d"))
        self.start_date = start_date

    def fetch_announcements(self, symbol: str):
        report_func = self.report_func or self._load_report_func()
        announcements = []
        seen_urls = set()
        for category in self.REPORT_CATEGORIES:
            frame = report_func(
                symbol=symbol,
                market="沪深京",
                category=category,
                start_date=self.start_date,
                end_date=self.today(),
            )
            if getattr(frame, "empty", False):
                continue
            for row in frame.to_dict("records"):
                announcement = self._normalize_row(row)
                if not announcement or announcement["url"] in seen_urls:
                    continue
                seen_urls.add(announcement["url"])
                announcements.append(announcement)
        return announcements

    def fetch_content(self, url: str) -> bytes:
        import requests

        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.content

    @staticmethod
    def _load_report_func():
        import akshare as ak

        return ak.stock_zh_a_disclosure_report_cninfo

    @staticmethod
    def _normalize_row(row: dict):
        title = str(row.get("公告标题") or "").strip()
        url = str(row.get("公告链接") or "").strip()
        if not title or not url:
            return None
        return {
            "title": title,
            "url": url,
            "document_type": _document_type_from_title(title),
            "report_period": _report_period_from_title(title),
            "disclosure_date": _date_from_announcement_time(row.get("公告时间")),
        }


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
        self.client = client or AkshareCninfoClient()

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


def _document_type_from_title(title: str) -> str:
    if "年度报告" in title or re.search(r"\d{4}年年报", title):
        return "annual_report"
    if any(marker in title for marker in ("第一季度报告", "一季报", "第三季度报告", "三季报", "半年度报告", "半年报")):
        return "quarterly_report"
    return "announcement"


def _report_period_from_title(title: str) -> str | None:
    match = re.search(r"(?P<year>\d{4})年", title)
    if not match:
        return None
    year = match.group("year")
    if "第一季度报告" in title or "一季报" in title:
        return f"{year}Q1"
    if "半年度报告" in title or "半年报" in title:
        return f"{year}Q2"
    if "第三季度报告" in title or "三季报" in title:
        return f"{year}Q3"
    if "年度报告" in title or "年报" in title:
        return f"{year}Q4"
    return None


def _date_from_announcement_time(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nat", "none"}:
        return None
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if match:
        return match.group(0)
    digits = re.search(r"\d{8}", text)
    if digits:
        raw = digits.group(0)
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return None
