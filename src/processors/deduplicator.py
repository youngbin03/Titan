"""
뉴스 기사 중복 제거
1. URL 정규화 후 exact match
2. 제목 유사도 (SequenceMatcher)
"""
from difflib import SequenceMatcher
from urllib.parse import urlparse, urlencode, parse_qs
from loguru import logger


class Deduplicator:

    def __init__(self, title_similarity_threshold: float = 0.80):
        self.threshold = title_similarity_threshold

    def deduplicate(self, articles: list[dict]) -> list[dict]:
        if not articles:
            return []

        sorted_articles = sorted(
            articles,
            key=lambda a: str(a.get("published_at") or ""),
            reverse=True,
        )

        seen_urls: set[str] = set()
        seen_titles: list[str] = []
        unique: list[dict] = []

        for article in sorted_articles:
            url = self._normalize_url(article.get("url", ""))
            title = article.get("title", "").strip().lower()

            if not url and not title:
                continue

            if url and url in seen_urls:
                continue

            is_dup = False
            for existing_title in seen_titles:
                ratio = SequenceMatcher(None, title, existing_title).ratio()
                if ratio >= self.threshold:
                    is_dup = True
                    break

            if is_dup:
                continue

            if url:
                seen_urls.add(url)
            if title:
                seen_titles.append(title)
            unique.append(article)

        removed = len(articles) - len(unique)
        if removed > 0:
            logger.debug(f"중복 제거: {len(articles)}개 → {len(unique)}개 (-{removed})")

        return unique

    def _normalize_url(self, url: str) -> str:
        if not url:
            return ""
        try:
            parsed = urlparse(url.lower().strip())
            exclude_params = {"utm_source", "utm_medium", "utm_campaign", "utm_content",
                              "utm_term", "ref", "source", "fbclid", "gclid", "_ga"}
            qs = parse_qs(parsed.query)
            filtered_qs = {k: v for k, v in qs.items() if k not in exclude_params}
            normalized = parsed._replace(query=urlencode(filtered_qs, doseq=True), fragment="")
            return normalized.geturl()
        except Exception:
            return url.lower().strip()
