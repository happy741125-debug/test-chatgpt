from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.access import OpsAccess
from app.dependencies import SessionDependency
from app.intelligence.followup import FollowupItem, followup_queue, mark_overdue

router = APIRouter(prefix="/api/followups", tags=["followups"])


class FollowupResponse(BaseModel):
    id: str
    title: str
    status: str
    priority_level: str
    domain_code: str
    owner_text: str | None
    deadline_at: datetime | None
    requires_user_action: bool
    overdue: bool

    @classmethod
    def from_item(cls, item: FollowupItem) -> FollowupResponse:
        return cls(
            id=item.id,
            title=item.title,
            status=item.status,
            priority_level=item.priority_level,
            domain_code=item.domain_code,
            owner_text=item.owner_text,
            deadline_at=item.deadline_at,
            requires_user_action=item.requires_user_action,
            overdue=item.overdue,
        )


class ScanResult(BaseModel):
    overdue_marked: int


@router.get("")
def list_followups(
    _: OpsAccess,
    session: SessionDependency,
    due_within_hours: int = Query(default=24, ge=1, le=336),
) -> list[FollowupResponse]:
    items = followup_queue(session, due_within_hours=due_within_hours)
    return [FollowupResponse.from_item(item) for item in items]


@router.post("/scan")
def scan_followups(_: OpsAccess, session: SessionDependency) -> ScanResult:
    # session.get_bind() gives us the same engine; reuse a fresh session factory
    # via the request session's bind so the scan runs in its own transaction.
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    return ScanResult(overdue_marked=mark_overdue(factory))
