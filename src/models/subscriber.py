from sqlalchemy import Column, String, DateTime, Boolean, Integer
from datetime import datetime, timezone
import uuid
from .database import Base


class Subscriber(Base):
    __tablename__ = "subscribers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
    confirmed = Column(Boolean, default=True)   # MVP: 즉시 활성화
    signal_threshold = Column(Integer, default=30)  # 수신할 최소 신호 스코어

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_sent_at = Column(DateTime(timezone=True))

    def __repr__(self):
        return f"<Subscriber {self.email} active={self.is_active}>"
