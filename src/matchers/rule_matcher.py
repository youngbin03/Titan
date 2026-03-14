"""
이벤트-뉴스 매칭 (규칙 기반 + 선택적 임베딩)
"""
from difflib import SequenceMatcher
from datetime import datetime, timezone, timedelta
from loguru import logger
from src.config import settings


class RuleMatcher:

    def match(
        self,
        event: dict,
        articles: list[dict],
        top_k: int = 5,
    ) -> list[tuple[dict, float]]:
        """
        이벤트와 가장 관련있는 기사 top_k개 반환
        Returns: [(article, relevance_score), ...]
        """
        if not articles:
            return []

        event_keywords = set(k.lower() for k in (event.get("keywords") or []))
        event_entities = set(e.lower() for e in (event.get("entities") or []))
        event_title = (event.get("title") or "").lower()

        scored: list[tuple[dict, float]] = []

        for article in articles:
            score = self._score_article(
                article, event_keywords, event_entities, event_title
            )
            if score > 0.1:  # 최소 관련성 임계값
                scored.append((article, score))

        # 점수 내림차순 정렬
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _score_article(
        self,
        article: dict,
        event_keywords: set,
        event_entities: set,
        event_title: str,
    ) -> float:
        score = 0.0

        art_title = (article.get("title") or "").lower()
        art_desc = (article.get("description") or "").lower()
        art_text = f"{art_title} {art_desc}"

        art_words = set(art_text.split())

        # 1. 키워드 오버랩 (40점)
        if event_keywords:
            kw_overlap = len(event_keywords & art_words) / len(event_keywords)
            score += kw_overlap * 0.40

        # 2. 엔티티 오버랩 (30점)
        if event_entities:
            ent_score = 0
            for entity in event_entities:
                if entity in art_text:
                    ent_score += 1
            ent_overlap = ent_score / len(event_entities)
            score += ent_overlap * 0.30

        # 3. 제목 직접 유사도 (20점)
        title_similarity = SequenceMatcher(None, event_title[:100], art_title[:100]).ratio()
        score += title_similarity * 0.20

        # 4. 시간 근접성 (10점)
        published = article.get("published_at")
        if published:
            if isinstance(published, str):
                try:
                    published = datetime.fromisoformat(published)
                except Exception:
                    published = None

            if published:
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                hours_diff = abs(
                    (datetime.now(timezone.utc) - published).total_seconds() / 3600
                )
                time_score = max(0, 1 - hours_diff / 48)  # 48시간 기준
                score += time_score * 0.10

        return round(score, 4)
