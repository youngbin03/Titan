"""
예측시장 이벤트에서 투자 신호를 감지하고 스코어링
"""
from datetime import datetime, timezone
from loguru import logger
from src.config import settings


class SignalDetector:

    def calculate_score(self, market: dict) -> float:
        """
        신호 스코어 계산 (0~100)
        - 확률 변동 (0~40점)
        - 거래량 급증 (0~30점)
        - 절대 거래량 (0~15점)
        - 잔여 기간 (0~15점)
        """
        score = 0.0

        # 1. 확률 변동 (6h 기준, 없으면 24h 사용)
        delta_6h = abs(market.get("price_delta_6h") or 0)
        delta_24h = abs(market.get("price_delta_24h") or 0)
        delta = max(delta_6h, delta_24h * 0.5)  # 24h는 가중치 절반
        score += min(delta * 400, 40)  # 10%p 변동 = 40점

        # 2. 거래량 급증
        volume_24h = float(market.get("volume_24h") or 0)
        avg_volume_7d = float(market.get("avg_volume_7d") or 1)
        volume_ratio = volume_24h / max(avg_volume_7d, 1)
        score += min(volume_ratio * 10, 30)  # 3배 = 30점

        # 3. 절대 거래량 ($)
        total_volume = float(market.get("total_volume") or 0)
        score += min(total_volume / 100_000 * 15, 15)  # $100K = 15점

        # 4. 잔여 기간 가중치
        end_date = market.get("end_date")
        if end_date:
            now = datetime.now(timezone.utc)
            if isinstance(end_date, datetime):
                if end_date.tzinfo is None:
                    end_date = end_date.replace(tzinfo=timezone.utc)
                days_left = (end_date - now).days
                if days_left <= 7:
                    score += 15
                elif days_left <= 30:
                    score += 10
                elif days_left <= 90:
                    score += 5

        # 현재 가격이 너무 극단적이면 감점 (0.95 이상 or 0.05 이하 = 이미 결론난 마켓)
        current_price = float(market.get("current_price") or 0.5)
        if current_price >= 0.95 or current_price <= 0.05:
            score *= 0.5

        return round(min(score, 100), 2)

    def filter_signals(self, markets: list[dict]) -> list[dict]:
        """임계값 이상의 신호만 반환 (스코어 내림차순)"""
        signals = []
        for m in markets:
            score = self.calculate_score(m)
            if score >= settings.signal_score_threshold:
                m["signal_score"] = score
                signals.append(m)

        signals.sort(key=lambda x: x["signal_score"], reverse=True)
        logger.info(f"신호 감지: {len(markets)}개 중 {len(signals)}개 (threshold={settings.signal_score_threshold})")
        return signals

    def is_urgent(self, score: float) -> bool:
        return score >= settings.urgent_signal_threshold

    def classify_signal_type(self, market: dict) -> str:
        """신호 유형 분류"""
        delta = abs(market.get("price_delta_6h") or market.get("price_delta_24h") or 0)
        volume_ratio = (
            (market.get("volume_24h") or 0) / max(market.get("avg_volume_7d") or 1, 1)
        )

        if delta >= 0.15:
            return "probability_spike"
        elif volume_ratio >= 3.0:
            return "volume_surge"
        elif market.get("signal_score", 0) >= 50:
            return "high_activity"
        else:
            return "trending"
