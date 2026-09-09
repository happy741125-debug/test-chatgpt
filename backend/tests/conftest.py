from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db import Database
from app.main import create_app
from app.queue import InMemoryJobQueue


@pytest.fixture
def test_context():
    settings = Settings(
        app_env="test",
        ops_api_token="test-ops-token",
        upload_api_token="test-upload-token",
        database_url="sqlite+pysqlite:///:memory:",
        line_channel_secret="test-channel-secret",
        line_channel_access_token="",
        line_silent_mode=True,
        auto_create_schema=True,
    )
    database = Database(settings.database_url)
    queue = InMemoryJobQueue()
    app = create_app(settings=settings, database=database, queue=queue)
    try:
        with TestClient(app) as client:
            yield client, database, queue
    finally:
        database.engine.dispose()
