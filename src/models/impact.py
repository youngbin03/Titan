from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from .database import Base


class CompanyImpact(Base):
    __tablename__ = "company_impacts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String(36), ForeignKey("events.id"), nullable=False)
    ticker = Column(String(20), nullable=False)
    company_name = Column(String(255))

    impact_type = Column(String(10))        # positive | negative | neutral | mixed
    impact_score = Column(Integer)          # 1~10
    confidence = Column(Float)              # 0~1
    duration = Column(String(10))          # immediate | short | medium | long

    reasoning = Column(Text)
    reasoning_ko = Column(Text)
    affected_metrics = Column(JSON, default=list)

    event = relationship("Event", back_populates="impacts")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Impact {self.ticker}: {self.impact_type} score={self.impact_score}>"
