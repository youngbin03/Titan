from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional
import os


class Settings(BaseSettings):
    # LLM
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # News APIs
    newsapi_key: str = ""
    naver_client_id: str = ""
    naver_client_secret: str = ""
    kalshi_api_key: str = ""

    # Email
    resend_api_key: str = ""
    email_from: str = "signal@titan.local"
    email_to: str = ""

    # Signal thresholds
    signal_score_threshold: float = 30.0
    urgent_signal_threshold: float = 70.0
    max_events_per_email: int = 5
    max_articles_per_event: int = 5

    # Paths
    output_dir: str = "./output"
    database_url: str = "sqlite+aiosqlite:///./titan_signal.db"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def email_recipients(self) -> list[str]:
        if not self.email_to:
            return []
        return [e.strip() for e in self.email_to.split(",") if e.strip()]

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_resend(self) -> bool:
        return bool(self.resend_api_key)

    @property
    def has_newsapi(self) -> bool:
        return bool(self.newsapi_key)

    @property
    def has_naver(self) -> bool:
        return bool(self.naver_client_id and self.naver_client_secret)


settings = Settings()
