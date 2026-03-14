"""
이메일 HTML 조립
"""
import os
from datetime import datetime, timezone, timedelta
from jinja2 import Environment, FileSystemLoader
from loguru import logger


DURATION_LABELS = {
    "immediate": "즉시",
    "short": "단기(1~7일)",
    "medium": "중기(1~3개월)",
    "long": "장기(3개월+)",
}

IMPACT_LABELS = {
    "positive": "호재",
    "negative": "악재",
    "neutral": "중립",
    "mixed": "혼재",
}

IMPACT_EMOJIS = {
    "positive": "🟢",
    "negative": "🔴",
    "neutral": "⚪",
    "mixed": "🟡",
}


class EmailComposer:

    def __init__(self):
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def compose(self, pipeline_results: list[dict]) -> tuple[str, str]:
        """
        파이프라인 결과를 이메일 HTML로 조립
        Returns: (subject, html_content)
        """
        now_kst = datetime.now(timezone(timedelta(hours=9)))
        generated_at = now_kst.strftime("%Y년 %m월 %d일 %H:%M KST")

        signal_items = []
        total_companies = 0
        total_articles = 0

        for result in pipeline_results:
            event = result["event"]
            articles = result.get("articles", [])
            analysis = result.get("analysis", {})
            impacts_raw = analysis.get("companies", [])

            # 뉴스 포맷팅
            formatted_articles = []
            for article in articles[:5]:
                published = article.get("published_at")
                pub_ago = self._format_time_ago(published)
                source = article.get("source", "Unknown").replace("newsapi:", "")
                formatted_articles.append({
                    "title": article.get("title", "")[:80],
                    "url": article.get("url", "#"),
                    "source": source,
                    "published_ago": pub_ago,
                })

            # 기업 영향 포맷팅
            formatted_impacts = []
            for imp in impacts_raw[:8]:
                ticker = imp.get("ticker", "")
                company = result.get("company_map", {}).get(ticker, {})
                formatted_impacts.append({
                    "ticker": ticker,
                    "company_ko": company.get("name_ko") or company.get("name") or "",
                    "impact_type": imp.get("impact_type", "neutral"),
                    "impact_label": IMPACT_LABELS.get(imp.get("impact_type", "neutral"), "중립"),
                    "impact_emoji": IMPACT_EMOJIS.get(imp.get("impact_type", "neutral"), "⚪"),
                    "impact_score": imp.get("impact_score", 5),
                    "duration_label": DURATION_LABELS.get(imp.get("duration", "short"), "단기"),
                    "reasoning_ko": imp.get("reasoning_ko", ""),
                    "confidence": imp.get("confidence", 0.5),
                })

            total_companies += len(formatted_impacts)
            total_articles += len(formatted_articles)

            price_delta = round((event.get("price_delta_6h") or event.get("price_delta_24h") or 0) * 100, 1)

            signal_items.append({
                "event_title": event.get("title", ""),
                "event_url": event.get("url", ""),
                "current_price": round((event.get("current_price") or 0.5) * 100, 1),
                "price_delta": price_delta,
                "signal_score": round(event.get("signal_score") or 0),
                "category": event.get("category", ""),
                "event_summary_ko": analysis.get("event_summary_ko", ""),
                "investment_implication_ko": analysis.get("investment_implication_ko", ""),
                "articles": formatted_articles,
                "impacts": formatted_impacts,
            })

        # 상단 이벤트 기준 제목 생성
        if signal_items:
            top_event = signal_items[0]["event_title"][:40]
            subject = f"📊 [{now_kst.strftime('%m/%d')}] {top_event}... 외 {len(signal_items)-1}건"
        else:
            subject = f"📊 [{now_kst.strftime('%m/%d')}] TITAN Signal 데일리 리포트"

        template = self.env.get_template("email.html")
        html = template.render(
            subject=subject,
            generated_at=generated_at,
            total_events=len(signal_items),
            total_companies=total_companies,
            total_articles=total_articles,
            signal_items=signal_items,
        )

        return subject, html

    def _format_time_ago(self, dt) -> str:
        if not dt:
            return "Unknown"
        try:
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            diff = datetime.now(timezone.utc) - dt
            hours = int(diff.total_seconds() / 3600)
            if hours < 1:
                return "방금 전"
            elif hours < 24:
                return f"{hours}시간 전"
            else:
                return f"{int(hours/24)}일 전"
        except Exception:
            return ""
