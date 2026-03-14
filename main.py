"""
TITAN Signal — 메인 진입점

사용법:
  python main.py serve    # 웹 서버 시작 (API + 스케줄러 통합)
  python main.py run      # 파이프라인 1회 실행
  python main.py test     # API 연결 테스트
  python main.py schedule # 스케줄러만 실행 (데몬 모드, 웹 없음)
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from loguru import logger
from rich.console import Console

console = Console()


def setup_logging():
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
        level="INFO",
    )
    os.makedirs("logs", exist_ok=True)
    logger.add(
        "logs/titan_{time:YYYY-MM-DD}.log",
        rotation="1 day", retention="7 days",
        level="DEBUG", encoding="utf-8",
    )


async def cmd_serve(host: str = "0.0.0.0", port: int = None):
    """웹 서버 + API + 스케줄러 통합 실행"""
    import uvicorn
    from src.models.database import init_db

    # Render는 PORT 환경변수를 주입함
    port = port or int(os.environ.get("PORT", 8000))

    await init_db()

    console.print(f"\n[bold green]TITAN Signal 서버 시작[/bold green]")
    console.print(f"  웹: [cyan]http://localhost:{port}[/cyan]")
    console.print(f"  API: [cyan]http://localhost:{port}/api[/cyan]")
    console.print(f"  스케줄러: 오전 8시 / 오후 6시 자동 실행")
    console.print(f"  종료: Ctrl+C\n")

    config = uvicorn.Config(
        "src.api.app:app",
        host=host, port=port,
        log_level="warning",
        reload=False,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def cmd_run():
    """파이프라인 1회 실행"""
    from src.models.database import init_db
    from src.pipeline.orchestrator import PipelineOrchestrator

    await init_db()
    orchestrator = PipelineOrchestrator()
    result = await orchestrator.run(dry_run=False)
    return result


async def cmd_schedule():
    """스케줄러 데몬 실행 (웹 없음)"""
    from src.models.database import init_db
    from src.pipeline.scheduler import PipelineScheduler

    await init_db()
    scheduler = PipelineScheduler()

    console.print("[bold green]TITAN Signal 스케줄러 시작[/bold green]")
    console.print("오전 8시, 오후 6시 KST 정기 발송 + 30분마다 긴급 신호 체크")
    console.print("종료: Ctrl+C\n")

    scheduler.start()
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.stop()
        console.print("\n[yellow]스케줄러 중지[/yellow]")


async def cmd_test():
    """API 연결 테스트"""
    from src.config import settings
    from src.collectors import PolymarketCollector, GDELTCollector

    console.print("[bold]API 연결 테스트[/bold]\n")
    console.print("📋 설정 확인:")
    console.print(f"  Anthropic API: {'✅' if settings.anthropic_api_key and not settings.anthropic_api_key.startswith('sk-ant-...') else '❌ 없음 (규칙기반 분석 사용)'}")
    console.print(f"  NewsAPI: {'✅' if settings.has_newsapi else '⚠️  없음 (GDELT만 사용)'}")
    console.print(f"  Naver News: {'✅' if settings.has_naver else '⚠️  없음'}")
    console.print(f"  Resend 이메일: {'✅' if settings.has_resend else '⚠️  없음 (파일 저장만)'}")
    console.print()

    console.print("🔌 Polymarket API...")
    try:
        markets = await PolymarketCollector().fetch_active_markets(limit=5)
        console.print(f"  ✅ {len(markets)}개 마켓 수집: {markets[0]['title'][:60]}")
    except Exception as e:
        console.print(f"  ❌ {e}")

    console.print("\n🔌 GDELT API...")
    try:
        articles = await GDELTCollector().search("market economy", timespan="24h", max_results=3)
        console.print(f"  ✅ {len(articles)}개 기사 수집")
    except Exception as e:
        console.print(f"  ❌ {e}")

    console.print("\n[green]테스트 완료[/green]")


def main():
    setup_logging()
    os.makedirs("output", exist_ok=True)

    args = sys.argv[1:]
    command = args[0] if args else "serve"

    if command == "serve":
        port = int(args[1]) if len(args) > 1 else 8000
        asyncio.run(cmd_serve(port=port))
    elif command == "run":
        asyncio.run(cmd_run())
    elif command == "schedule":
        asyncio.run(cmd_schedule())
    elif command == "test":
        asyncio.run(cmd_test())
    else:
        console.print(f"[red]알 수 없는 명령어: {command}[/red]")
        console.print("사용법: python main.py [serve|run|schedule|test]")
        sys.exit(1)


if __name__ == "__main__":
    main()
