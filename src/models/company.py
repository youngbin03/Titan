from sqlalchemy import Column, String, Float, DateTime, JSON, Text, Boolean
from datetime import datetime, timezone
from .database import Base


class Company(Base):
    __tablename__ = "companies"

    ticker = Column(String(20), primary_key=True)
    name = Column(String(255), nullable=False)
    name_ko = Column(String(255))
    sector = Column(String(50))
    market = Column(String(5))          # US | KR

    keywords = Column(JSON, default=list)
    supply_chain = Column(JSON, default=list)
    competitors = Column(JSON, default=list)
    revenue_exposure = Column(JSON, default=dict)   # {"china": 0.19, "us": 0.43}
    related_sectors = Column(JSON, default=list)

    market_cap = Column(Float)
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Company {self.ticker}: {self.name}>"
