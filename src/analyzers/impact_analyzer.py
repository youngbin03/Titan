"""
Claude API를 이용한 기업 영향 분석
"""
import json
from anthropic import AsyncAnthropic, AuthenticationError
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.config import settings


IMPACT_PROMPT = """당신은 시니어 주식 애널리스트입니다. 아래 예측시장 이벤트와 관련 뉴스를 분석하여 각 기업에 미치는 영향을 판단하세요.

## 이벤트 정보
- 제목: {event_title}
- 현재 확률: {current_price}%
- 6시간 전 확률: {price_6h_ago}% (변동: {price_delta:+.1f}%p)
- 카테고리: {category}

## 관련 뉴스 요약
{news_summary}

## 분석 대상 기업
{company_info}

## 응답 형식 (반드시 유효한 JSON만 출력)
```json
{{
  "event_summary_ko": "이벤트 한국어 요약 (2-3문장)",
  "investment_implication_ko": "투자 시사점 한국어 (2-3문장)",
  "companies": [
    {{
      "ticker": "종목코드",
      "impact_type": "positive|negative|neutral|mixed",
      "impact_score": 1~10 (숫자만),
      "confidence": 0.0~1.0 (확신도),
      "duration": "immediate|short|medium|long",
      "affected_metrics": ["revenue", "margin", "supply_chain", "demand", "regulation"],
      "reasoning_ko": "영향 근거 한국어 (1-2문장)"
    }}
  ]
}}
```

duration 기준: immediate(1일이내) | short(1~7일) | medium(1~3개월) | long(3개월+)
impact_score 기준: 1~3(미미) | 4~6(중간) | 7~9(직접/상당) | 10(매우심각)
JSON만 출력하고 다른 텍스트는 포함하지 마세요."""


class ImpactAnalyzer:

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    async def analyze(
        self,
        event: dict,
        articles: list[dict],
        companies: list[dict],
    ) -> dict:
        """기업 영향 분석 (Claude API 또는 규칙 기반 폴백)"""
        # API 키 유효성 1차 체크
        api_key = settings.anthropic_api_key or ""
        if not api_key or api_key.startswith("sk-ant-...") or len(api_key) < 20:
            logger.warning("Anthropic API 키 없음 - 규칙 기반 폴백 사용")
            return self._fallback_analysis(event, companies)

        if not companies:
            return {"companies": [], "event_summary_ko": "", "investment_implication_ko": ""}

        try:
            return await self._analyze_with_claude(event, articles, companies)
        except AuthenticationError:
            logger.warning("Anthropic 인증 실패 - 규칙 기반 폴백 사용")
            return self._fallback_analysis(event, companies)
        except Exception as e:
            logger.warning(f"Claude 분석 실패 ({e}) - 규칙 기반 폴백 사용")
            return self._fallback_analysis(event, companies)

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(min=3, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _analyze_with_claude(
        self,
        event: dict,
        articles: list[dict],
        companies: list[dict],
    ) -> dict:
        """Claude API 실제 호출"""
        # 뉴스 요약 구성 (최대 5개)
        news_lines = []
        for i, article in enumerate(articles[:5], 1):
            title = article.get("title", "")
            desc = (article.get("description") or "")[:100]
            source = article.get("source", "")
            news_lines.append(f"{i}. [{source}] {title}\n   {desc}")
        news_summary = "\n".join(news_lines) if news_lines else "관련 뉴스 없음"

        # 기업 정보 구성
        company_lines = []
        for c in companies:
            exposure = c.get("revenue_exposure", {})
            exposure_str = ", ".join([f"{k.upper()} {v*100:.0f}%" for k, v in list(exposure.items())[:3]])
            company_lines.append(
                f"- {c['ticker']} ({c.get('name_ko') or c['name']}): "
                f"섹터={c.get('sector', 'N/A')}, "
                f"매출 노출={exposure_str}"
            )
        company_info = "\n".join(company_lines)

        prompt = IMPACT_PROMPT.format(
            event_title=event.get("title", ""),
            current_price=round((event.get("current_price") or 0.5) * 100, 1),
            price_6h_ago=round((event.get("price_6h_ago") or 0.5) * 100, 1),
            price_delta=round((event.get("price_delta_6h") or 0) * 100, 1),
            category=event.get("category", "General"),
            news_summary=news_summary,
            company_info=company_info,
        )

        client = self._get_client()
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        content = response.content[0].text.strip()

        # JSON 추출
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        result = self._calibrate(result, event)
        logger.info(f"영향 분석 완료: {len(result.get('companies', []))}개 기업")
        return result

    def _calibrate(self, result: dict, event: dict) -> dict:
        """확률 변동 크기에 따른 영향 스코어 보정"""
        delta = abs(event.get("price_delta_6h") or event.get("price_delta_24h") or 0)
        probability_factor = min(delta / 0.10, 1.5)
        current_price = event.get("current_price") or 0.5

        for company in result.get("companies", []):
            if probability_factor > 0:
                company["impact_score"] = min(10, max(1, round(
                    company.get("impact_score", 5) * probability_factor
                )))
            if current_price < 0.30:
                company["impact_score"] = max(1, company.get("impact_score", 5) - 2)
            if company.get("confidence", 1.0) < 0.5:
                company["caveat"] = "분석 확신도 낮음 — 추가 확인 권장"
        return result

    def _fallback_analysis(self, event: dict, companies: list[dict]) -> dict:
        """API 키 없거나 인증 실패 시 규칙 기반 폴백"""
        title_lower = (event.get("title") or "").lower()

        negative_kw = ["tariff", "sanction", "ban", "war", "crisis", "recession",
                       "default", "conflict", "crash", "collapse", "fine", "penalty"]
        positive_kw = ["deal", "agreement", "growth", "win", "approve", "peace",
                       "merger", "acquisition", "breakthrough", "approval", "record"]

        impact_type = "neutral"
        for kw in negative_kw:
            if kw in title_lower:
                impact_type = "negative"
                break
        for kw in positive_kw:
            if kw in title_lower:
                impact_type = "positive"
                break

        delta = abs(event.get("price_delta_6h") or event.get("price_delta_24h") or 0)
        base_score = min(10, max(3, int(delta * 100)))

        event_summary = f"예측시장 이벤트: {event.get('title', '')} (확률: {round((event.get('current_price') or 0.5)*100)}%)"

        return {
            "event_summary_ko": event_summary,
            "investment_implication_ko": "정확한 분석을 위해 .env 파일에 ANTHROPIC_API_KEY를 설정하세요.",
            "companies": [
                {
                    "ticker": c["ticker"],
                    "impact_type": impact_type,
                    "impact_score": base_score,
                    "confidence": 0.4,
                    "duration": "short",
                    "affected_metrics": ["general"],
                    "reasoning_ko": f"{c.get('name_ko') or c['name']}에 간접 영향 가능성 (규칙 기반)",
                }
                for c in companies[:5]
            ],
        }
