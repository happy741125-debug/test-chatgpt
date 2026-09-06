from __future__ import annotations

import hmac
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.dependencies import JobQueueDependency, SessionDependency
from app.models import JobStatus, ProcessingJob, utc_now

router = APIRouter(prefix="/ops", tags=["operations"])


def require_ops_access(
    request: Request,
    ops_token: Annotated[str | None, Header(alias="X-Ops-Token")] = None,
) -> None:
    expected = request.app.state.settings.ops_api_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_code": "OPS_API_NOT_CONFIGURED"},
        )
    if not ops_token or not hmac.compare_digest(ops_token, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "OPS_ACCESS_DENIED"},
        )


OpsAccess = Annotated[None, Depends(require_ops_access)]


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_type: str
    status: str
    attempts: int
    max_attempts: int
    available_at: datetime
    last_error: str | None


@router.get("/jobs/dead-letter")
def list_dead_letter_jobs(
    _: OpsAccess,
    session: SessionDependency,
) -> list[JobResponse]:
    jobs = session.scalars(
        select(ProcessingJob)
        .where(ProcessingJob.status == JobStatus.DEAD_LETTER.value)
        .order_by(ProcessingJob.updated_at.desc())
    ).all()
    return [JobResponse.model_validate(job) for job in jobs]


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: str,
    _: OpsAccess,
    session: SessionDependency,
    queue: JobQueueDependency,
) -> JobResponse:
    job = session.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "JOB_NOT_FOUND"},
        )
    if job.status not in {
        JobStatus.DEAD_LETTER.value,
        JobStatus.RETRY_SCHEDULED.value,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "JOB_NOT_RETRYABLE", "current_status": job.status},
        )

    job.status = JobStatus.QUEUED.value
    job.attempts = 0
    job.available_at = utc_now()
    job.last_error = None
    session.commit()
    session.refresh(job)
    try:
        queue.publish(job.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "QUEUE_UNAVAILABLE",
                "message": "工作已保存為待處理，可在 Queue 恢復後再次送出。",
            },
        ) from exc
    return JobResponse.model_validate(job)
