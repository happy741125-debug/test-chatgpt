from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from threading import Event, Thread

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.channels import router as channels_router
from app.api.contexts import router as contexts_router
from app.api.executive import router as executive_router
from app.api.gmail import router as gmail_router
from app.api.intelligence import router as intelligence_router
from app.api.operational_performance import router as operational_performance_router
from app.api.operations import router as operations_router
from app.api.revenue import router as revenue_router
from app.api.weekly_reviews import router as weekly_reviews_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, correlation_id
from app.db import Database
from app.dependencies import JobQueueDependency, SessionDependency
from app.line.security import verify_signature
from app.metrics import (
    LINE_EVENTS_ACCEPTED,
    LINE_EVENTS_DUPLICATE,
    LINE_INVALID_SIGNATURES,
    LINE_MESSAGES_CREATED,
    QUEUE_PUBLISH_FAILURES,
    metrics_response,
)
from app.queue import JobQueue, RedisJobQueue
from app.services.ingestion import ingest_line_payload

logger = logging.getLogger(__name__)


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
        stop_event: Event | None = None
        worker_thread: Thread | None = None
        if resolved_settings.embedded_worker_enabled:
            from app.worker import run_worker_loop

            stop_event = Event()
            worker_thread = Thread(
                target=run_worker_loop,
                args=(resolved_settings, resolved_database, resolved_queue),
                kwargs={"stop_event": stop_event},
                name="workhub-embedded-worker",
                daemon=True,
            )
            worker_thread.start()
            logger.info("Embedded worker enabled")
        try:
            yield
        finally:
            if stop_event is not None:
                stop_event.set()
            if worker_thread is not None:
                worker_thread.join(timeout=6)

    app = FastAPI(
        title="Work Intelligence Hub API",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = resolved_database
    app.state.queue = resolved_queue
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://huoda-work-intelligence-dashboard.onrender.com"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-Ops-Token"],
    )
    app.include_router(channels_router)
    app.include_router(contexts_router)
    app.include_router(executive_router)
    app.include_router(gmail_router)
    app.include_router(intelligence_router)
    app.include_router(operations_router)
    app.include_router(operational_performance_router)
    app.include_router(revenue_router)
    app.include_router(weekly_reviews_router)

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

    @app.get("/health/release")
    def release() -> dict[str, str]:
        return {"release": "2026.09.08-v3.1-cross-source-operations-v1"}

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

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return metrics_response()

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
            LINE_INVALID_SIGNATURES.inc()
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
        LINE_EVENTS_ACCEPTED.inc(result.events_accepted)
        LINE_EVENTS_DUPLICATE.inc(result.events_duplicate)
        LINE_MESSAGES_CREATED.inc(result.messages_created)
        published = 0
        for job_id in result.job_ids:
            try:
                job_queue.publish(job_id)
                published += 1
            except Exception:  # noqa: BLE001 - durable DB job can be replayed later
                QUEUE_PUBLISH_FAILURES.inc()
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
