"""
NewsAPI.org 수집기 (선택적)
https://newsapi.org — 무료 100req/일
"""
import httpx
from datetime import datetime, timezone, timedelta
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from src.config import settings


NEWSAPI_BASE = "https://newsapi.org/v2"


class NewsAPICollector:

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def search(self, query: str, max_results: int = 10) -> list[dict]:
        if not settings.has_newsapi:
            return []

        async with httpx.AsyncClient(timeout=20) as client:
            try:
                from_date = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
                # ASCII 범위 밖 문자 제거 (NewsAPI 요건)
                safe_query = query.encode("ascii", errors="ignore").decode("ascii")
                if not safe_query.strip():
                    return []

                resp = await client.get(
                    f"{NEWSAPI_BASE}/everything",
                    params={
                        "q": safe_query,
                        "language": "en",
                        "sortBy": "publishedAt",
                        "pageSize": max_results,
                        "from": from_date,
                    },
                    headers={"X-Api-Key": settings.newsapi_key},
                )
                resp.raise_for_status()
                data = resp.json()

                articles = []
                for item in data.get("articles", []):
                    try:
                        articles.append(self._parse_article(item))
                    except Exception:
                        continue

                logger.info(f"NewsAPI '{query}': {len(articles)}개 기사 수집")
                return articles

            except Exception as e:
                logger.warning(f"NewsAPI error '{query}': {e}")
                return []

    def _parse_article(self, raw: dict) -> dict:
        published = raw.get("publishedAt")
        dt = None
        if published:
            try:
                dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except Exception:
                dt = datetime.now(timezone.utc)

        return {
            "source": f"newsapi:{raw.get('source', {}).get('name', '')}",
            "url": raw.get("url", ""),
            "title": raw.get("title", ""),
            "description": raw.get("description", ""),
            "content": raw.get("content", "") or raw.get("description", ""),
            "author": raw.get("author", ""),
            "published_at": dt,
            "language": "en",
        }
