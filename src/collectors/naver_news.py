"""
네이버 뉴스 검색 API 수집기
https://developers.naver.com (무료, 25,000건/일)
"""
import httpx
from datetime import datetime, timezone
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from src.config import settings


NAVER_NEWS_API = "https://openapi.naver.com/v1/search/news.json"


class NaverNewsCollector:

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
    async def search(self, query: str, max_results: int = 10) -> list[dict]:
        """네이버 뉴스 검색"""
        if not settings.has_naver:
            logger.debug("Naver API 키 없음, 건너뜀")
            return []

        async with httpx.AsyncClient(timeout=20) as client:
            try:
                resp = await client.get(
                    NAVER_NEWS_API,
                    params={"query": query, "display": max_results, "sort": "date"},
                    headers={
                        "X-Naver-Client-Id": settings.naver_client_id,
                        "X-Naver-Client-Secret": settings.naver_client_secret,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                articles = []
                for item in data.get("items", []):
                    try:
                        articles.append(self._parse_article(item))
                    except Exception:
                        continue

                logger.info(f"Naver '{query}': {len(articles)}개 기사 수집")
                return articles

            except Exception as e:
                logger.warning(f"Naver news error '{query}': {e}")
                return []

    def _clean_html(self, text: str) -> str:
        import re
        return re.sub(r"<[^>]+>", "", text or "").strip()

    def _parse_article(self, raw: dict) -> dict:
        return {
            "source": "naver",
            "url": raw.get("originallink") or raw.get("link", ""),
            "title": self._clean_html(raw.get("title", "")),
            "description": self._clean_html(raw.get("description", "")),
            "content": self._clean_html(raw.get("description", "")),
            "author": "",
            "published_at": self._parse_date(raw.get("pubDate")),
            "language": "ko",
        }

    def _parse_date(self, date_str) -> datetime | None:
        if not date_str:
            return datetime.now(timezone.utc)
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str).astimezone(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)
