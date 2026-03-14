"""
이벤트/뉴스에서 영향 받는 기업 후보 매핑
"""
import json
import os
from loguru import logger


class CompanyMapper:

    def __init__(self):
        self.companies: list[dict] = []
        self._load_companies()

    def _load_companies(self):
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        for filename in ("companies_us.json", "companies_kr.json"):
            filepath = os.path.join(data_dir, filename)
            try:
                with open(filepath, encoding="utf-8") as f:
                    self.companies.extend(json.load(f))
            except Exception as e:
                logger.warning(f"기업 데이터 로드 실패 {filename}: {e}")

        logger.info(f"기업 매핑 로드: {len(self.companies)}개")

    def find_relevant_companies(
        self,
        event_title: str,
        event_description: str,
        articles: list[dict],
        max_companies: int = 8,
    ) -> list[dict]:
        """이벤트/뉴스에서 관련 기업 후보 추출"""
        text = f"{event_title} {event_description} "
        for article in articles[:5]:
            text += f"{article.get('title', '')} {article.get('description', '')} "
        text = text.lower()

        scored: list[tuple[dict, float]] = []

        for company in self.companies:
            score = self._score_company(company, text)
            if score > 0:
                scored.append((company, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        # 결과 반환 (US 5개 + KR 3개 균형)
        us_companies = [(c, s) for c, s in scored if c.get("market") == "US"][:5]
        kr_companies = [(c, s) for c, s in scored if c.get("market") == "KR"][:3]

        combined = us_companies + kr_companies
        combined.sort(key=lambda x: x[1], reverse=True)

        return [c for c, _ in combined[:max_companies]]

    def _score_company(self, company: dict, text: str) -> float:
        score = 0.0
        keywords = company.get("keywords", [])
        name = company.get("name", "").lower()
        name_ko = company.get("name_ko", "").lower()

        # 키워드 매칭
        for kw in keywords:
            if kw.lower() in text:
                score += 1.0

        # 이름 직접 매칭 (가중치 높음)
        if name in text:
            score += 3.0
        if name_ko and name_ko in text:
            score += 3.0

        # 섹터 관련 점수 (간접 영향)
        sector = company.get("sector", "").lower()
        sector_keywords = {
            "technology": ["tech", "software", "hardware", "chip", "semiconductor", "ai", "cloud"],
            "energy": ["oil", "gas", "energy", "opec", "crude", "petroleum", "refinery"],
            "financial": ["bank", "rate", "fed", "interest", "financial", "credit"],
            "consumer discretionary": ["tariff", "trade", "consumer", "retail"],
            "materials": ["battery", "lithium", "rare earth", "material"],
        }
        for sec_kw in sector_keywords.get(sector, []):
            if sec_kw in text:
                score += 0.3

        # 노출도 기반 가중치 (예: 중국 관련 이슈 → 중국 매출 비중 높은 기업 우선)
        revenue_exposure = company.get("revenue_exposure", {})
        if "china" in text and revenue_exposure.get("china", 0) > 0.15:
            score += revenue_exposure["china"] * 5

        return score

    def get_company_by_ticker(self, ticker: str) -> dict | None:
        for c in self.companies:
            if c["ticker"].upper() == ticker.upper():
                return c
        return None
