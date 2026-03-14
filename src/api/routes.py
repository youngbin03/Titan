"""
FastAPI 라우트 — 구독 관리 + 대시보드 API
"""
import os
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from src.models.database import async_session
from src.models.subscriber import Subscriber
from src.models.event import Event

router = APIRouter()


# ─── Pydantic Schemas ────────────────────────────────────────────
class SubscribeRequest(BaseModel):
    email: str

class UnsubscribeRequest(BaseModel):
    email: str

class SubscribeResponse(BaseModel):
    success: bool
    message: str
    email: str


# ─── DB Dependency ───────────────────────────────────────────────
async def get_db():
    async with async_session() as session:
        yield session


# ─── Routes ──────────────────────────────────────────────────────

@router.post("/api/subscribe", response_model=SubscribeResponse)
async def subscribe(req: SubscribeRequest, db: AsyncSession = Depends(get_db)):
    """이메일 구독"""
    email = req.email.strip().lower()

    # 간단한 이메일 유효성 검사
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="유효하지 않은 이메일 주소입니다.")

    # 이미 존재하는지 확인
    result = await db.execute(select(Subscriber).where(Subscriber.email == email))
    existing = result.scalar_one_or_none()

    if existing:
        if existing.is_active:
            return SubscribeResponse(
                success=False,
                message="이미 구독 중인 이메일입니다.",
                email=email,
            )
        else:
            # 재구독
            existing.is_active = True
            await db.commit()
            logger.info(f"재구독: {email}")
            return SubscribeResponse(
                success=True,
                message="구독이 재활성화되었습니다.",
                email=email,
            )

    # 신규 구독
    subscriber = Subscriber(email=email)
    db.add(subscriber)
    await db.commit()
    logger.info(f"신규 구독: {email}")

    return SubscribeResponse(
        success=True,
        message="구독 완료! 다음 신호가 감지되면 이메일로 알려드립니다.",
        email=email,
    )


@router.post("/api/unsubscribe")
async def unsubscribe(req: UnsubscribeRequest, db: AsyncSession = Depends(get_db)):
    """이메일 구독 해지"""
    email = req.email.strip().lower()
    result = await db.execute(select(Subscriber).where(Subscriber.email == email))
    sub = result.scalar_one_or_none()

    if not sub:
        raise HTTPException(status_code=404, detail="구독 정보를 찾을 수 없습니다.")

    sub.is_active = False
    await db.commit()
    logger.info(f"구독 해지: {email}")
    return {"success": True, "message": "구독이 해지되었습니다."}


@router.get("/api/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """대시보드 통계"""
    from sqlalchemy import func

    # 구독자 수
    sub_count = await db.execute(
        select(func.count()).where(Subscriber.is_active == True)
    )
    subscriber_count = sub_count.scalar() or 0

    # 감지된 이벤트 수 (최근 24시간)
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    event_count = await db.execute(
        select(func.count()).select_from(Event).where(Event.created_at >= since)
    )
    recent_events = event_count.scalar() or 0

    # 최근 이벤트 목록
    recent_q = await db.execute(
        select(Event)
        .order_by(Event.signal_score.desc())
        .limit(5)
    )
    recent_signals = recent_q.scalars().all()

    signals_data = [
        {
            "title": e.title[:80],
            "score": round(e.signal_score or 0),
            "price": round((e.current_price or 0.5) * 100),
            "delta": round((e.price_delta_6h or 0) * 100, 1),
            "category": e.category or "",
            "url": e.url or "",
        }
        for e in recent_signals
    ]

    # 최근 발송된 이메일 수
    from src.models.email_dispatch import EmailDispatch
    dispatch_count = await db.execute(
        select(func.count()).select_from(EmailDispatch).where(
            EmailDispatch.status == "sent"
        )
    )
    emails_sent = dispatch_count.scalar() or 0

    return {
        "subscriber_count": subscriber_count,
        "recent_events_24h": recent_events,
        "emails_sent_total": emails_sent,
        "recent_signals": signals_data,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/run-now")
async def run_pipeline_now():
    """파이프라인 즉시 실행 트리거 (관리용)"""
    import asyncio
    from src.pipeline.orchestrator import PipelineOrchestrator

    async def _run():
        orch = PipelineOrchestrator()
        await orch.run(dry_run=False)

    # 백그라운드 태스크로 실행
    asyncio.create_task(_run())
    return {"success": True, "message": "파이프라인 실행이 시작되었습니다."}
