"""
이메일 발송 (Resend API 또는 로컬 파일 저장)
구독자 DB에 등록된 모든 활성 수신자에게 발송
"""
import os
from datetime import datetime, timezone, timedelta
from loguru import logger
from src.config import settings


class EmailSender:

    async def send(self, subject: str, html_content: str) -> dict:
        """
        이메일 발송
        1. 로컬 HTML 파일 저장 (항상)
        2. DB 구독자 목록으로 실제 발송 (Resend 키 있을 때)
        """
        output_path = await self._save_to_file(subject, html_content)

        recipients = await self._get_all_recipients()
        sent = False

        if settings.has_resend and recipients:
            sent = await self._send_via_resend(subject, html_content, recipients)
        else:
            if not settings.has_resend:
                logger.info("Resend API 키 없음 - 로컬 파일로만 저장")
            elif not recipients:
                logger.info("구독자 없음 - 로컬 파일로만 저장")

        return {
            "output_path": output_path,
            "sent": sent,
            "recipients": recipients,
        }

    async def _get_all_recipients(self) -> list[str]:
        """DB에서 활성 구독자 이메일 목록 조회 + .env 수신자 병합"""
        emails = list(settings.email_recipients)  # .env 설정 수신자

        try:
            from src.models.database import async_session
            from src.models.subscriber import Subscriber
            from sqlalchemy import select

            async with async_session() as db:
                result = await db.execute(
                    select(Subscriber.email).where(Subscriber.is_active == True)
                )
                db_emails = [row[0] for row in result.fetchall()]
                for e in db_emails:
                    if e not in emails:
                        emails.append(e)
        except Exception as e:
            logger.warning(f"구독자 DB 조회 실패: {e}")

        return emails

    async def _save_to_file(self, subject: str, html_content: str) -> str:
        os.makedirs(settings.output_dir, exist_ok=True)
        now_kst = datetime.now(timezone(timedelta(hours=9)))
        filename = f"signal_{now_kst.strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(settings.output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"이메일 저장: {filepath}")
        return filepath

    async def _send_via_resend(
        self, subject: str, html_content: str, recipients: list[str]
    ) -> bool:
        try:
            import resend
            resend.api_key = settings.resend_api_key

            # Resend는 한 번에 최대 50명 — 배치 처리
            batch_size = 50
            success_count = 0
            for i in range(0, len(recipients), batch_size):
                batch = recipients[i:i + batch_size]
                params = {
                    "from": settings.email_from,
                    "to": batch,
                    "subject": subject,
                    "html": html_content,
                }
                resend.Emails.send(params)
                success_count += len(batch)

            logger.info(f"이메일 발송 완료: {success_count}명")

            # DB 발송 기록 업데이트
            await self._mark_sent(recipients)
            return True

        except Exception as e:
            logger.error(f"이메일 발송 실패: {e}")
            return False

    async def _mark_sent(self, recipients: list[str]):
        try:
            from src.models.database import async_session
            from src.models.subscriber import Subscriber
            from sqlalchemy import select

            now = datetime.now(timezone.utc)
            async with async_session() as db:
                result = await db.execute(
                    select(Subscriber).where(Subscriber.email.in_(recipients))
                )
                for sub in result.scalars().all():
                    sub.last_sent_at = now
                await db.commit()
        except Exception as e:
            logger.warning(f"발송 기록 업데이트 실패: {e}")
