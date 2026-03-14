"""
APScheduler 기반 파이프라인 스케줄링
"""
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from src.pipeline.orchestrator import PipelineOrchestrator


class PipelineScheduler:

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
        self.orchestrator = PipelineOrchestrator()

    def start(self):
        # 매일 오전 8시 KST - 아침 데일리 리포트
        self.scheduler.add_job(
            self._run_scheduled,
            CronTrigger(hour=8, minute=0, timezone="Asia/Seoul"),
            id="morning_digest",
            name="아침 데일리 리포트",
            replace_existing=True,
        )

        # 매일 오후 6시 KST - 저녁 데일리 리포트
        self.scheduler.add_job(
            self._run_scheduled,
            CronTrigger(hour=18, minute=0, timezone="Asia/Seoul"),
            id="evening_digest",
            name="저녁 데일리 리포트",
            replace_existing=True,
        )

        # 30분마다 급등 시그널 체크 (발송은 urgent_threshold 이상일 때만)
        self.scheduler.add_job(
            self._run_urgent_check,
            IntervalTrigger(minutes=30),
            id="urgent_check",
            name="긴급 신호 모니터링",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info("스케줄러 시작: 오전 8시 / 오후 6시 정기 발송, 30분마다 긴급 체크")

    def stop(self):
        self.scheduler.shutdown()
        logger.info("스케줄러 중지")

    async def _run_scheduled(self):
        logger.info("정기 파이프라인 실행")
        try:
            await self.orchestrator.run(dry_run=False)
        except Exception as e:
            logger.error(f"정기 파이프라인 실패: {e}")

    async def _run_urgent_check(self):
        """긴급 신호만 체크 - 임계값 이상일 때만 이메일 발송"""
        logger.debug("긴급 신호 체크")
        try:
            from src.collectors import PolymarketCollector
            from src.processors import SignalDetector
            from src.config import settings

            collector = PolymarketCollector()
            detector = SignalDetector()

            markets = await collector.fetch_active_markets(limit=100)
            signals = detector.filter_signals(markets)

            urgent = [s for s in signals if detector.is_urgent(s.get("signal_score", 0))]
            if urgent:
                logger.info(f"긴급 신호 {len(urgent)}개 감지 - 즉시 분석 실행")
                await self.orchestrator.run(dry_run=False)

        except Exception as e:
            logger.error(f"긴급 체크 실패: {e}")
