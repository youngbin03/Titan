"""
이벤트 제목/설명에서 검색 키워드와 엔티티 추출
spaCy 없을 경우 규칙 기반 폴백 사용
"""
import re
from loguru import logger


# 불용어 (이벤트 제목에서 자주 나오지만 검색에 불필요한 단어)
STOP_WORDS = {
    "will", "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "have", "has", "do", "does", "did", "to", "of", "in", "on", "at",
    "by", "for", "with", "from", "that", "this", "these", "those",
    "what", "when", "where", "who", "which", "how", "why",
    "before", "after", "during", "while", "until", "since",
    "it", "its", "he", "she", "they", "we", "you", "i",
    "get", "end", "win", "lose", "make", "take", "give", "go",
    "2024", "2025", "2026", "2027", "2028", "january", "february",
    "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "q1", "q2", "q3", "q4",
}

# 도메인별 동의어/관련어 확장 사전
SYNONYM_MAP = {
    "tariff": ["trade war", "import duty", "customs", "trade restriction"],
    "election": ["vote", "ballot", "polling", "electoral", "candidate"],
    "fed": ["federal reserve", "interest rate", "monetary policy", "rate hike", "FOMC"],
    "recession": ["economic downturn", "GDP contraction", "economic slowdown"],
    "ai": ["artificial intelligence", "machine learning", "LLM", "generative AI"],
    "crypto": ["bitcoin", "cryptocurrency", "blockchain", "digital asset"],
    "war": ["conflict", "military", "invasion", "ceasefire"],
    "merger": ["acquisition", "M&A", "takeover", "deal"],
    "bankruptcy": ["default", "insolvency", "chapter 11", "restructuring"],
    "oil": ["crude", "petroleum", "energy", "OPEC"],
    "china": ["beijing", "sino", "PRC", "chinese"],
    "russia": ["moscow", "kremlin", "russian"],
    "israel": ["gaza", "middle east", "hamas"],
    "iran": ["tehran", "persian"],
}


class KeywordExtractor:

    def __init__(self):
        self._nlp = None
        self._spacy_available = False
        self._try_load_spacy()

    def _try_load_spacy(self):
        try:
            import spacy
            try:
                self._nlp = spacy.load("en_core_web_sm")
                self._spacy_available = True
                logger.info("spaCy 로드 성공 (NER 활성화)")
            except OSError:
                logger.warning("spaCy 모델 없음 (규칙 기반 모드로 실행)")
        except ImportError:
            logger.warning("spaCy 미설치 (규칙 기반 모드로 실행)")

    def extract(self, title: str, description: str = "") -> dict:
        """키워드와 엔티티 추출"""
        text = f"{title} {description}"

        if self._spacy_available and self._nlp:
            return self._extract_with_spacy(text)
        else:
            return self._extract_rule_based(title, description)

    def _extract_with_spacy(self, text: str) -> dict:
        doc = self._nlp(text[:512])  # 길이 제한

        # 엔티티 추출 (인명, 기관, 국가, 제품)
        entities = []
        for ent in doc.ents:
            if ent.label_ in ("ORG", "PERSON", "GPE", "PRODUCT", "EVENT", "LAW"):
                entities.append(ent.text.strip())

        # 키워드 추출 (명사, 고유명사)
        keywords = []
        for token in doc:
            if (token.pos_ in ("NOUN", "PROPN") and
                    not token.is_stop and
                    len(token.text) > 2 and
                    token.text.lower() not in STOP_WORDS):
                keywords.append(token.lemma_.lower())

        return {
            "keywords": list(dict.fromkeys(keywords))[:10],  # 중복 제거, 최대 10개
            "entities": list(dict.fromkeys(entities))[:8],
        }

    def _extract_rule_based(self, title: str, description: str = "") -> dict:
        """spaCy 없을 때 규칙 기반 추출"""
        text = f"{title} {description}"

        # 대문자로 시작하는 단어 = 잠재적 엔티티
        entities = re.findall(r'\b[A-Z][a-z]{2,}\b(?:\s+[A-Z][a-z]{2,})*', text)
        entities = [e for e in entities if e.lower() not in STOP_WORDS]

        # 소문자 명사구 추출
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        keywords = [w for w in words if w not in STOP_WORDS and len(w) > 3]

        # 중복 제거 후 빈도 기반 정렬
        from collections import Counter
        keyword_freq = Counter(keywords)
        top_keywords = [k for k, _ in keyword_freq.most_common(10)]

        return {
            "keywords": top_keywords,
            "entities": list(dict.fromkeys(entities))[:8],
        }

    def generate_search_queries(self, title: str, description: str = "") -> list[str]:
        """뉴스 검색용 쿼리 생성"""
        extracted = self.extract(title, description)
        keywords = extracted["keywords"]
        entities = extracted["entities"]

        queries = []

        # 쿼리 1: 상위 엔티티 조합
        if len(entities) >= 2:
            queries.append(" ".join(entities[:2]))
        elif entities:
            queries.append(entities[0])

        # 쿼리 2: 핵심 키워드 + 엔티티
        if keywords and entities:
            queries.append(f"{entities[0] if entities else ''} {keywords[0] if keywords else ''}".strip())

        # 쿼리 3: 제목 압축 (30자 이내)
        clean_title = re.sub(r'\b(will|the|a|an|by|in|on|at|to|of|for)\b', '', title.lower()).strip()
        clean_title = re.sub(r'\s+', ' ', clean_title)[:60]
        if clean_title and clean_title not in queries:
            queries.append(clean_title)

        # 쿼리 4: 동의어 확장
        for kw in keywords[:3]:
            if kw in SYNONYM_MAP:
                related = SYNONYM_MAP[kw]
                queries.append(f"{kw} {related[0]}")
                break

        # 중복 제거 + 빈 쿼리 제거
        queries = list(dict.fromkeys([q.strip() for q in queries if q.strip()]))
        return queries[:4]  # 최대 4개 쿼리

    def generate_korean_queries(self, title: str, entities: list[str]) -> list[str]:
        """한국어 뉴스 검색용 쿼리 (주요 단어 번역)"""
        # 기본 번역 사전 (핵심 투자 용어)
        ko_map = {
            "tariff": "관세", "trade": "무역", "war": "전쟁",
            "china": "중국", "us": "미국", "korea": "한국",
            "election": "선거", "fed": "연준", "rate": "금리",
            "inflation": "인플레이션", "recession": "경기침체",
            "bitcoin": "비트코인", "crypto": "암호화폐",
            "oil": "유가", "energy": "에너지",
            "semiconductor": "반도체", "chip": "반도체",
            "ai": "인공지능", "merger": "인수합병",
            "russia": "러시아", "ukraine": "우크라이나",
            "israel": "이스라엘", "iran": "이란",
            "trump": "트럼프", "biden": "바이든",
            "nuclear": "핵", "sanction": "제재",
        }

        queries = []
        title_lower = title.lower()

        for en, ko in ko_map.items():
            if en in title_lower:
                queries.append(ko)

        # 엔티티의 한국어명
        entity_ko_map = {
            "Apple": "애플", "Samsung": "삼성", "Tesla": "테슬라",
            "Microsoft": "마이크로소프트", "Google": "구글",
            "Amazon": "아마존", "Meta": "메타", "Nvidia": "엔비디아",
            "China": "중국", "US": "미국", "Russia": "러시아",
        }
        for entity in entities:
            if entity in entity_ko_map:
                queries.append(entity_ko_map[entity])

        queries = list(dict.fromkeys(queries))[:3]
        return queries
