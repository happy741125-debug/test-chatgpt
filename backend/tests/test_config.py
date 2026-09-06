from __future__ import annotations

from app.core.config import Settings


def test_render_postgres_url_uses_psycopg_driver() -> None:
    settings = Settings(
        database_url="postgresql://user:password@example.com:5432/workhub",
        _env_file=None,
    )

    assert settings.database_url == (
        "postgresql+psycopg://user:password@example.com:5432/workhub"
    )


def test_legacy_postgres_url_uses_psycopg_driver() -> None:
    settings = Settings(
        database_url="postgres://user:password@example.com:5432/workhub",
        _env_file=None,
    )

    assert settings.database_url == (
        "postgresql+psycopg://user:password@example.com:5432/workhub"
    )


def test_explicit_driver_url_is_not_changed() -> None:
    url = "postgresql+psycopg://user:password@example.com:5432/workhub"

    settings = Settings(database_url=url, _env_file=None)

    assert settings.database_url == url
