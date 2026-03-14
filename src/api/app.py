"""
FastAPI 애플리케이션 — 웹 서버 + API + 스케줄러 통합
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from loguru import logger

from src.models.database import init_db
from src.api.routes import router
from src.pipeline.scheduler import PipelineScheduler

_scheduler: PipelineScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작
    logger.info("TITAN Signal 서버 시작")
    await init_db()
    logger.info("DB 초기화 완료")

    global _scheduler
    _scheduler = PipelineScheduler()
    _scheduler.start()

    yield

    # 종료
    if _scheduler:
        _scheduler.stop()
    logger.info("서버 종료")


app = FastAPI(
    title="TITAN Signal",
    description="예측시장 기반 투자 이벤트 큐레이션 서비스",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터
app.include_router(router)

# 정적 파일 (웹 에셋)
web_dir = os.path.join(os.path.dirname(__file__), "..", "..", "web")
if os.path.exists(web_dir):
    app.mount("/static", StaticFiles(directory=web_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(web_dir, "index.html")
    with open(index_path, encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
