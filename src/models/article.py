from sqlalchemy import Column, String, Float, DateTime, JSON, Text
from datetime import datetime, timezone
import uuid
from .database import Base


class Article(Base):
    __tablename__ = "articles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String(50), nullable=False)
    url = Column(Text, nullable=False, unique=True)
    title = Column(Text, nullable=False)
    description = Column(Text)
    content = Column(Text)
    summary = Column(Text)          # LLM 생성 영문 요약
    summary_ko = Column(Text)       # 한국어 요약

    author = Column(String(255))
    published_at = Column(DateTime(timezone=True))
    language = Column(String(5))

    keywords = Column(JSON, default=list)
    entities = Column(JSON, default=list)

    # 매칭된 이벤트 ID 목록
    matched_event_ids = Column(JSON, default=list)
    relevance_score = Column(Float, default=0)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Article {self.source}: {self.title[:60]}...>"
