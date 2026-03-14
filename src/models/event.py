from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from .database import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String(20), nullable=False)        # polymarket | kalshi
    source_id = Column(String(255), nullable=False, unique=True)
    title = Column(Text, nullable=False)
    description = Column(Text)
    category = Column(String(50))
    url = Column(Text)

    # 가격/확률
    current_price = Column(Float)
    price_6h_ago = Column(Float)
    price_24h_ago = Column(Float)
    price_delta_6h = Column(Float)
    price_delta_24h = Column(Float)

    # 거래량
    volume_1h = Column(Float, default=0)
    volume_24h = Column(Float, default=0)
    avg_volume_7d = Column(Float, default=0)
    total_volume = Column(Float, default=0)

    # 신호 스코어
    signal_score = Column(Float, default=0)
    is_processed = Column(Boolean, default=False)

    # 메타
    keywords = Column(JSON, default=list)       # ["tariff", "china", "trade"]
    entities = Column(JSON, default=list)       # ["US", "China", "Apple"]
    end_date = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    impacts = relationship("CompanyImpact", back_populates="event", lazy="selectin")

    def __repr__(self):
        return f"<Event {self.source_id}: {self.title[:50]}... score={self.signal_score:.1f}>"
