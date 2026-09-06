from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, correlation_id
from app.db import Database
from app.line.security import verify_signature
from app.queue import JobQueue, RedisJobQueue
from app.services.ingestion import ingest_line_payload

logger = logging.getLogger(__name__)


def get_session(request: Request) -> Iterator[Session]:
    database: Database = request.app.state.database
    yield from database.session()


def get_queue(request: Request) -> JobQueue:
    return request.app.state.queue


SessionDependency = Annotated[Session, Depends(get_session)]
JobQueueDependency = Annotated[JobQueue, Depends(get_queue)]


def create_app(
    *,
    settings: Settings | None = None,
    database: Database | None = None,
    queue: JobQueue | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    resolved_database = database or Database(resolved_settings.database_url)
    resolved_queue = queue or RedisJobQueue(
        resolved_settings.redis_url,
        queue_key=resolved_settings.redis_queue_key,
        retry_key=resolved_settings.redis_retry_key,
        dlq_key=resolved_settings.redis_dlq_key,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if resolved_settings.auto_create_schema:
            resolved_database.create_schema()
        yield

    app = FastAPI(
        title="Work Intelligence Hub API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = resolved_database
    app.state.queue = resolved_queue

    @app.middleware("http")
    async def add_correlation_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = correlation_id.set(request_id)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            correlation_id.reset(token)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled request error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error_code": "INTERNAL_ERROR",
                "message": "系統暫時無法處理這個請求。",
                "correlation_id": correlation_id.get(),
            },
        )

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready")
    def ready() -> dict[str, object]:
        checks: dict[str, bool] = {"database": False, "queue": False}
        try:
            checks["database"] = resolved_database.ping()
        except Exception:  # noqa: BLE001 - readiness must report rather than crash
            logger.exception("Database readiness check failed")
        try:
            checks["queue"] = resolved_queue.ping()
        except Exception:  # noqa: BLE001 - readiness must report rather than crash
            logger.exception("Queue readiness check failed")
        if not all(checks.values()):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "not_ready", "checks": checks},
            )
        return {"status": "ready", "checks": checks}

    @app.post("/webhooks/line")
    async def line_webhook(
        request: Request,
        session: SessionDependency,
        job_queue: JobQueueDependency,
    ) -> dict[str, int | str]:
        if not resolved_settings.line_channel_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error_code": "LINE_NOT_CONFIGURED",
                    "message": "LINE Channel Secret 尚未設定。",
                },
            )

        body = await request.body()
        signature = request.headers.get("X-Line-Signature")
        if not verify_signature(body, signature, resolved_settings.line_channel_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error_code": "INVALID_LINE_SIGNATURE"},
            )

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": "INVALID_JSON"},
            ) from exc
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": "INVALID_PAYLOAD"},
            )

        result = ingest_line_payload(
            session,
            payload,
            silent_mode=resolved_settings.line_silent_mode,
        )
        published = 0
        for job_id in result.job_ids:
            try:
                job_queue.publish(job_id)
                published += 1
            except Exception:  # noqa: BLE001 - durable DB job can be replayed later
                logger.exception(
                    "Queue publish failed; durable job remains queued",
                    extra={"job_id": job_id},
                )

        return {
            "status": "accepted",
            "events_accepted": result.events_accepted,
            "events_duplicate": result.events_duplicate,
            "messages_created": result.messages_created,
            "unsupported_events": result.unsupported_events,
            "jobs_published": published,
        }

    return app


app = create_app()
