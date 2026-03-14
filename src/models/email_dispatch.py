from sqlalchemy import Column, String, DateTime, JSON, Text
from datetime import datetime, timezone
import uuid
from .database import Base


class EmailDispatch(Base):
    __tablename__ = "email_dispatches"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dispatch_type = Column(String(20))      # scheduled | urgent
    event_ids = Column(JSON, default=list)

    subject = Column(Text)
    html_content = Column(Text)
    output_path = Column(Text)              # 로컬 파일 저장 경로

    recipients = Column(JSON, default=list)
    sent_at = Column(DateTime(timezone=True))
    status = Column(String(20), default="pending")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
