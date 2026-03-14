"""
GDELT Project 뉴스 수집기
완전 무료, API 키 불필요
"""
import httpx
import feedparser
from datetime import datetime, timezone
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
import re


GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


class GDELTCollector:

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def search(
        self,
        query: str,
        timespan: str = "24h",
        max_results: int = 10,
        lang: str = "English",
    ) -> list[dict]:
        """GDELT 뉴스 검색"""
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                params = {
                    "query": query,
                    "mode": "artlist",
                    "maxrecords": max_results,
                    "timespan": timespan,
                    "format": "json",
                    "sort": "datedesc",
                }
                if lang:
                    params["query"] = f"{query} sourcelang:{lang}"

                resp = await client.get(GDELT_DOC_API, params=params)
                resp.raise_for_status()
                data = resp.json()

                articles = []
                for item in data.get("articles", []):
                    try:
                        articles.append(self._parse_article(item))
                    except Exception as e:
                        logger.debug(f"GDELT parse error: {e}")
                        continue

                logger.info(f"GDELT '{query}': {len(articles)}개 기사 수집")
                return articles

            except httpx.HTTPStatusError as e:
                logger.warning(f"GDELT API error {e.response.status_code}: {query}")
                return []
            except Exception as e:
                logger.warning(f"GDELT error '{query}': {e}")
                return []

    def _parse_article(self, raw: dict) -> dict:
        return {
            "source": "gdelt",
            "url": raw.get("url", ""),
            "title": raw.get("title", ""),
            "description": raw.get("seendescription", ""),
            "content": raw.get("seendescription", ""),
            "author": raw.get("domain", ""),
            "published_at": self._parse_date(raw.get("seendate")),
            "language": raw.get("language", "English"),
        }

    def _parse_date(self, date_str) -> datetime | None:
        if not date_str:
            return None
        try:
            # GDELT 날짜 형식: "20241215T120000Z"
            cleaned = date_str.replace("T", "").replace("Z", "")
            if len(cleaned) >= 14:
                dt = datetime(
                    int(cleaned[0:4]), int(cleaned[4:6]), int(cleaned[6:8]),
                    int(cleaned[8:10]), int(cleaned[10:12]), int(cleaned[12:14]),
                    tzinfo=timezone.utc
                )
                return dt
        except Exception:
            pass
        return datetime.now(timezone.utc)
