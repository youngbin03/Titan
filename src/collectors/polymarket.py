"""
Polymarket CLOB API 수집기
Public API - 인증 불필요
"""
import httpx
from datetime import datetime, timezone
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential


POLYMARKET_CLOB_BASE = "https://clob.polymarket.com"
POLYMARKET_GAMMA_BASE = "https://gamma-api.polymarket.com"


class PolymarketCollector:
    def __init__(self):
        self.clob_base = POLYMARKET_CLOB_BASE
        self.gamma_base = POLYMARKET_GAMMA_BASE

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def fetch_active_markets(self, limit: int = 100) -> list[dict]:
        """활성 마켓 목록 조회 (Gamma API 사용 - 더 많은 메타데이터)"""
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                # Gamma API: 메타데이터 풍부
                resp = await client.get(
                    f"{self.gamma_base}/markets",
                    params={
                        "active": "true",
                        "closed": "false",
                        "limit": limit,
                        "order": "volume24hr",
                        "ascending": "false",
                    }
                )
                resp.raise_for_status()
                data = resp.json()

                markets = []
                for m in data:
                    try:
                        markets.append(self._parse_gamma_market(m))
                    except Exception as e:
                        logger.debug(f"Market parse error: {e}")
                        continue

                logger.info(f"Polymarket: {len(markets)}개 마켓 수집")
                return markets

            except httpx.HTTPStatusError as e:
                logger.error(f"Polymarket API error: {e.response.status_code}")
                raise
            except Exception as e:
                logger.error(f"Polymarket fetch error: {e}")
                raise

    def _parse_gamma_market(self, raw: dict) -> dict:
        """Gamma API 응답 파싱"""
        # 가격 처리 (outcome tokens에서 YES 가격 추출)
        tokens = raw.get("tokens", [])
        yes_price = 0.5
        for token in tokens:
            if token.get("outcome", "").upper() in ("YES", "TRUE", "1"):
                yes_price = float(token.get("price", 0.5))
                break

        # 24h 전 가격 (없으면 현재가와 동일로 처리)
        price_24h = float(raw.get("oneDayPriceChange", 0) or 0)
        price_6h = float(raw.get("sixHourPriceChange", 0) or 0)

        return {
            "source": "polymarket",
            "source_id": str(raw.get("id", raw.get("conditionId", ""))),
            "title": raw.get("question", raw.get("title", "")),
            "description": raw.get("description", ""),
            "category": raw.get("category", ""),
            "url": f"https://polymarket.com/event/{raw.get('slug', '')}",
            "current_price": yes_price,
            "price_24h_ago": yes_price - price_24h,
            "price_6h_ago": yes_price - price_6h,
            "price_delta_24h": price_24h,
            "price_delta_6h": price_6h,
            "volume_24h": float(raw.get("volume24hr", 0) or 0),
            "total_volume": float(raw.get("volume", 0) or 0),
            "volume_1h": 0,             # Gamma API에서 제공 안함
            "avg_volume_7d": float(raw.get("volume24hr", 0) or 0),  # 근사값
            "end_date": self._parse_date(raw.get("endDate") or raw.get("endDateIso")),
        }

    def _parse_date(self, date_str) -> datetime | None:
        if not date_str:
            return None
        try:
            dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None
