from __future__ import annotations

from functools import lru_cache

from pydantic import Field
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
    context_buffer_seconds: int = Field(default=180, ge=30, le=600)
    context_window_minutes: int = Field(default=15, ge=1, le=60)
    context_max_messages: int = Field(default=30, ge=2, le=100)
    auto_create_schema: bool = False

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
