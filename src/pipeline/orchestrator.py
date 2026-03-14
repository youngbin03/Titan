"""
전체 파이프라인 오케스트레이터
Stage 1: 이벤트 수집 → Stage 2: 신호 감지 → Stage 3: 뉴스 수집
→ Stage 4: 매칭 → Stage 5: 기업 분석 → Stage 6: 이메일 생성/발송
"""
import asyncio
from datetime import datetime, timezone
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import print as rprint

from src.collectors import PolymarketCollector, GDELTCollector, NaverNewsCollector
from src.collectors.newsapi import NewsAPICollector
from src.processors import SignalDetector, KeywordExtractor, Deduplicator
from src.matchers import RuleMatcher
from src.analyzers import CompanyMapper, ImpactAnalyzer
from src.generators import EmailComposer, EmailSender
from src.config import settings

console = Console()


class PipelineOrchestrator:

    def __init__(self):
        # Collectors
        self.polymarket = PolymarketCollector()
        self.gdelt = GDELTCollector()
        self.naver = NaverNewsCollector()
        self.newsapi = NewsAPICollector()

        # Processors
        self.signal_detector = SignalDetector()
        self.keyword_extractor = KeywordExtractor()
        self.deduplicator = Deduplicator()

        # Matchers
        self.matcher = RuleMatcher()

        # Analyzers
        self.company_mapper = CompanyMapper()
        self.impact_analyzer = ImpactAnalyzer()

        # Generators
        self.email_composer = EmailComposer()
        self.email_sender = EmailSender()

    async def run(self, dry_run: bool = False) -> dict:
        """
        전체 파이프라인 실행
        dry_run=True: 이메일 실제 발송/저장 없이 결과만 반환
        """
        start_time = datetime.now(timezone.utc)
        console.rule("[bold purple]TITAN Signal Pipeline[/bold purple]")

        # ─── Stage 1: 이벤트 수집 ───────────────────────────────
        console.print("\n[bold cyan]Stage 1:[/bold cyan] 예측시장 이벤트 수집 중...")
        raw_markets = await self.polymarket.fetch_active_markets(limit=200)
        console.print(f"  → Polymarket {len(raw_markets)}개 마켓 수집")

        # ─── Stage 2: 신호 감지 ──────────────────────────────────
        console.print("\n[bold cyan]Stage 2:[/bold cyan] 신호 감지 중...")
        signals = self.signal_detector.filter_signals(raw_markets)

        if not signals:
            console.print("[yellow]  → 임계값 이상 신호 없음[/yellow]")
            return {"pipeline_results": [], "stats": self._empty_stats(start_time)}

        # 상위 N개만 처리
        top_signals = signals[:settings.max_events_per_email]
        self._print_signals_table(top_signals)

        # ─── Stage 3~5: 이벤트별 뉴스 수집 + 매칭 + 분석 ────────
        console.print(f"\n[bold cyan]Stage 3~5:[/bold cyan] {len(top_signals)}개 이벤트 심층 분석 중...")
        pipeline_results = []

        for i, market in enumerate(top_signals, 1):
            console.print(f"\n  [{i}/{len(top_signals)}] [white]{market['title'][:60]}...[/white]")

            result = await self._process_single_event(market)
            if result:
                pipeline_results.append(result)

        if not pipeline_results:
            logger.warning("분석 결과 없음")
            return {"pipeline_results": [], "stats": self._empty_stats(start_time)}

        # DB 저장
        await self._save_to_db(pipeline_results)

        # ─── Stage 6: 이메일 생성 + 발송 ─────────────────────────
        if not dry_run:
            console.print("\n[bold cyan]Stage 6:[/bold cyan] 이메일 생성 중...")
            subject, html = self.email_composer.compose(pipeline_results)
            send_result = await self.email_sender.send(subject, html)

            console.print(f"\n[bold green]✅ 완료![/bold green]")
            console.print(f"  이메일 저장: [cyan]{send_result['output_path']}[/cyan]")
            if send_result["sent"]:
                console.print(f"  발송 완료: {send_result['recipients']}")
        else:
            subject, html = self.email_composer.compose(pipeline_results)
            send_result = {"output_path": None, "sent": False}
            console.print("\n[yellow]  dry_run 모드: 이메일 발송 생략[/yellow]")

        # 통계
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        stats = {
            "total_markets": len(raw_markets),
            "signals_detected": len(signals),
            "events_analyzed": len(pipeline_results),
            "elapsed_seconds": round(elapsed, 1),
            "output_path": send_result.get("output_path"),
        }

        self._print_summary(stats)
        return {"pipeline_results": pipeline_results, "stats": stats}

    async def _process_single_event(self, market: dict) -> dict | None:
        """단일 이벤트 처리: 뉴스 수집 → 매칭 → 기업 분석"""
        try:
            # 키워드 추출
            extracted = self.keyword_extractor.extract(
                market.get("title", ""), market.get("description", "")
            )
            market["keywords"] = extracted["keywords"]
            market["entities"] = extracted["entities"]

            search_queries = self.keyword_extractor.generate_search_queries(
                market.get("title", ""), market.get("description", "")
            )
            ko_queries = self.keyword_extractor.generate_korean_queries(
                market.get("title", ""), extracted["entities"]
            )

            console.print(f"    키워드: {', '.join(extracted['keywords'][:5])}")
            console.print(f"    검색쿼리: {search_queries[:2]}")

            # 뉴스 수집 (GDELT는 순차, 나머지는 병렬)
            # GDELT는 rate limit이 있어서 순차 처리
            gdelt_articles = []
            for query in search_queries[:2]:
                result = await self.gdelt.search(query, timespan="24h", max_results=8)
                gdelt_articles.extend(result)
                await asyncio.sleep(1.5)  # GDELT rate limit 방지

            # 나머지 병렬
            other_tasks = []
            for kq in ko_queries[:2]:
                other_tasks.append(self.naver.search(kq, max_results=5))
            if settings.has_newsapi:
                for query in search_queries[:1]:
                    other_tasks.append(self.newsapi.search(query, max_results=5))

            other_results = await asyncio.gather(*other_tasks, return_exceptions=True)
            news_results = [gdelt_articles] + list(other_results)
            all_articles = []
            for result in news_results:
                if isinstance(result, list):
                    all_articles.extend(result)
                elif isinstance(result, Exception):
                    logger.debug(f"뉴스 수집 예외 (무시): {result}")

            # 중복 제거
            unique_articles = self.deduplicator.deduplicate(all_articles)
            console.print(f"    뉴스: {len(all_articles)}개 수집 → {len(unique_articles)}개 (중복제거)")

            # 이벤트-뉴스 매칭
            matched = self.matcher.match(market, unique_articles, top_k=settings.max_articles_per_event)
            matched_articles = [article for article, _ in matched]

            # 기업 후보 매핑
            companies = self.company_mapper.find_relevant_companies(
                market.get("title", ""),
                market.get("description", ""),
                matched_articles,
                max_companies=8,
            )
            console.print(f"    관련 기업 후보: {[c['ticker'] for c in companies]}")

            # LLM 영향 분석
            analysis = await self.impact_analyzer.analyze(market, matched_articles, companies)

            # 기업 매핑 딕셔너리 (템플릿용)
            company_map = {c["ticker"]: c for c in companies}

            return {
                "event": market,
                "articles": matched_articles,
                "analysis": analysis,
                "company_map": company_map,
            }

        except Exception as e:
            logger.error(f"이벤트 처리 실패 '{market.get('title', '')}': {e}")
            return None

    async def _save_to_db(self, pipeline_results: list[dict]):
        """처리된 이벤트와 영향 분석을 DB에 저장"""
        try:
            from src.models.database import async_session
            from src.models.event import Event
            from src.models.impact import CompanyImpact
            from sqlalchemy import select

            async with async_session() as db:
                for result in pipeline_results:
                    market = result["event"]
                    analysis = result.get("analysis", {})

                    # 이벤트 저장 (upsert)
                    existing = await db.execute(
                        select(Event).where(Event.source_id == market.get("source_id", ""))
                    )
                    event_obj = existing.scalar_one_or_none()

                    if not event_obj:
                        event_obj = Event(
                            source=market.get("source", "polymarket"),
                            source_id=market.get("source_id", ""),
                            title=market.get("title", ""),
                            description=market.get("description", ""),
                            category=market.get("category", ""),
                            url=market.get("url", ""),
                            current_price=market.get("current_price"),
                            price_6h_ago=market.get("price_6h_ago"),
                            price_24h_ago=market.get("price_24h_ago"),
                            price_delta_6h=market.get("price_delta_6h"),
                            price_delta_24h=market.get("price_delta_24h"),
                            volume_24h=market.get("volume_24h"),
                            total_volume=market.get("total_volume"),
                            signal_score=market.get("signal_score"),
                            keywords=market.get("keywords", []),
                            entities=market.get("entities", []),
                            end_date=market.get("end_date"),
                            is_processed=True,
                        )
                        db.add(event_obj)
                        await db.flush()

                        # 기업 영향 저장
                        company_map = result.get("company_map", {})
                        for imp in analysis.get("companies", []):
                            ticker = imp.get("ticker", "")
                            company = company_map.get(ticker, {})
                            impact_obj = CompanyImpact(
                                event_id=event_obj.id,
                                ticker=ticker,
                                company_name=company.get("name_ko") or company.get("name", ""),
                                impact_type=imp.get("impact_type", "neutral"),
                                impact_score=imp.get("impact_score", 5),
                                confidence=imp.get("confidence", 0.5),
                                duration=imp.get("duration", "short"),
                                reasoning_ko=imp.get("reasoning_ko", ""),
                                affected_metrics=imp.get("affected_metrics", []),
                            )
                            db.add(impact_obj)

                await db.commit()
                logger.info(f"DB 저장 완료: {len(pipeline_results)}개 이벤트")
        except Exception as e:
            logger.error(f"DB 저장 실패: {e}")

    def _print_signals_table(self, signals: list[dict]):
        table = Table(title="감지된 신호", border_style="purple")
        table.add_column("Score", style="bold yellow", width=7)
        table.add_column("확률", style="cyan", width=8)
        table.add_column("변동(6h)", width=10)
        table.add_column("이벤트", style="white")

        for s in signals[:10]:
            delta = s.get("price_delta_6h") or 0
            delta_str = f"{'+' if delta >= 0 else ''}{delta*100:.1f}%p"
            delta_style = "green" if delta >= 0 else "red"
            table.add_row(
                str(round(s.get("signal_score", 0))),
                f"{(s.get('current_price') or 0.5)*100:.0f}%",
                f"[{delta_style}]{delta_str}[/{delta_style}]",
                s.get("title", "")[:70],
            )

        console.print(table)

    def _print_summary(self, stats: dict):
        console.print(f"\n[bold]📊 파이프라인 요약[/bold]")
        console.print(f"  마켓 수집: {stats['total_markets']}개")
        console.print(f"  신호 감지: {stats['signals_detected']}개")
        console.print(f"  이벤트 분석: {stats['events_analyzed']}개")
        console.print(f"  소요 시간: {stats['elapsed_seconds']}초")
        if stats.get("output_path"):
            console.print(f"  결과 파일: {stats['output_path']}")

    def _empty_stats(self, start_time: datetime) -> dict:
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        return {
            "total_markets": 0, "signals_detected": 0,
            "events_analyzed": 0, "elapsed_seconds": round(elapsed, 1),
            "output_path": None,
        }
