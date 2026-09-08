from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    ops_api_token: str = Field(default="", repr=False)
    database_url: str = "sqlite+pysqlite:///./work-intelligence.db"
    redis_url: str = "redis://localhost:6379/0"
    redis_queue_key: str = "workhub:jobs"
    redis_retry_key: str = "workhub:jobs:retry"
    redis_dlq_key: str = "workhub:jobs:dlq"
    line_channel_secret: str = Field(default="", repr=False)
    line_channel_access_token: str = Field(default="", repr=False)
    line_silent_mode: bool = True
    gmail_client_id: str = Field(default="", repr=False)
    gmail_client_secret: str = Field(default="", repr=False)
    gmail_redirect_uri: str = "http://localhost:8000/api/gmail/callback"
    credential_encryption_secret: str = Field(default="", repr=False)
    dashboard_url: str = "http://localhost:3000"
    gmail_initial_sync_days: int = Field(default=7, ge=1, le=90)
    gmail_initial_sync_limit: int = Field(default=50, ge=1, le=200)
    gmail_sync_token: str = Field(default="", repr=False)
    context_buffer_seconds: int = Field(default=180, ge=30, le=600)
    context_window_minutes: int = Field(default=15, ge=1, le=60)
    context_max_messages: int = Field(default=30, ge=2, le=100)
    ai_provider: str = "disabled"
    shadow_enabled: bool = False
    shadow_provider: str = "gemini"  # "gemini" | "openai"
    gemini_api_key: str = Field(default="", repr=False)
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: str = Field(default="", repr=False)
    openai_model: str = "gpt-4o-mini"
    embedded_worker_enabled: bool = False
    auto_create_schema: bool = False

    @property
    def shadow_api_key(self) -> str:
        if self.shadow_provider == "openai":
            return self.openai_api_key
        return self.gemini_api_key

    @property
    def shadow_active(self) -> bool:
        return self.shadow_enabled and bool(self.shadow_api_key)

    @property
    def gmail_configured(self) -> bool:
        return bool(
            self.gmail_client_id
            and self.gmail_client_secret
            and self.credential_encryption_secret
            and self.gmail_redirect_uri
        )

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg_driver(cls, value: object) -> object:
        """Make managed PostgreSQL URLs use the installed psycopg v3 driver."""
        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
