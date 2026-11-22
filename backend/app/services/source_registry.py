from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ManagementSource, SourceAuthorizationAudit, Workspace, utc_now
from app.security.authorization import CLASSIFICATION_RANK

ALLOWED_SOURCE_TYPES = {"LINE", "GMAIL", "DOCUMENT", "API", "CALENDAR", "MANUAL"}
ALLOWED_RETENTION_POLICIES = {
    "REFERENCE_ONLY",
    "SOURCE_CONTROLLED",
    "30_DAYS",
    "90_DAYS",
    "365_DAYS",
    "LEGAL_HOLD",
}


@dataclass(frozen=True)
class SourceRegistrationResult:
    source: ManagementSource
    created: bool


def register_source(
    session: Session,
    *,
    workspace_id: str,
    source_type: str,
    external_source_key: str,
    name: str,
    authority_scope: str,
    actor_id: str,
    classification: str = "INTERNAL",
    retention_policy: str = "SOURCE_CONTROLLED",
    sync_mode: str = "READ_ONLY",
    freshness_threshold_hours: int | None = None,
    contains_sensitive_data: bool = False,
    source_url: str | None = None,
) -> SourceRegistrationResult:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None or workspace.status != "ACTIVE":
        raise ValueError("WORKSPACE_NOT_ACTIVE")

    normalized_type = source_type.strip().upper()
    normalized_key = external_source_key.strip()
    if normalized_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError("SOURCE_TYPE_NOT_ALLOWED")
    if not normalized_key:
        raise ValueError("EXTERNAL_SOURCE_KEY_REQUIRED")
    if classification not in CLASSIFICATION_RANK:
        raise ValueError("CLASSIFICATION_UNKNOWN")
    if retention_policy not in ALLOWED_RETENTION_POLICIES:
        raise ValueError("RETENTION_POLICY_NOT_ALLOWED")
    if freshness_threshold_hours is not None and freshness_threshold_hours < 1:
        raise ValueError("FRESHNESS_THRESHOLD_INVALID")

    existing = session.scalar(
        select(ManagementSource).where(
            ManagementSource.workspace_id == workspace_id,
            ManagementSource.source_type == normalized_type,
            ManagementSource.external_source_key == normalized_key,
        )
    )
    if existing is not None:
        return SourceRegistrationResult(source=existing, created=False)

    digest = hashlib.sha256(
        f"{workspace_id}:{normalized_type}:{normalized_key}".encode()
    ).hexdigest()[:12]
    safe_type = re.sub(r"[^A-Z0-9]+", "_", normalized_type).strip("_")
    source = ManagementSource(
        workspace_id=workspace_id,
        code=f"AICOS_{safe_type}_{digest}",
        name=name,
        source_type=normalized_type,
        external_source_key=normalized_key,
        authorization_status="PENDING",
        authorized_scopes_json=[],
        classification=classification,
        authority_scope=authority_scope,
        sync_mode=sync_mode,
        retention_policy=retention_policy,
        contains_sensitive_data=contains_sensitive_data,
        source_url=source_url,
        freshness_threshold_hours=freshness_threshold_hours,
    )
    session.add(source)
    session.flush()
    _audit(
        session,
        source=source,
        actor_id=actor_id,
        event_type="REGISTERED",
        before_status=None,
        after_status="PENDING",
        scopes=[],
    )
    return SourceRegistrationResult(source=source, created=True)


def authorize_source(
    session: Session,
    *,
    source_id: str,
    workspace_id: str,
    actor_id: str,
    scopes: list[str],
    now: datetime | None = None,
) -> ManagementSource:
    source = _workspace_source(session, source_id=source_id, workspace_id=workspace_id)
    before = source.authorization_status
    normalized_scopes = sorted({scope.strip() for scope in scopes if scope.strip()})
    source.authorization_status = "ACTIVE"
    source.authorized_scopes_json = normalized_scopes
    source.authorized_at = now or utc_now()
    source.revoked_at = None
    source.revocation_reason = None
    _audit(
        session,
        source=source,
        actor_id=actor_id,
        event_type="AUTHORIZED",
        before_status=before,
        after_status="ACTIVE",
        scopes=normalized_scopes,
    )
    return source


def revoke_source(
    session: Session,
    *,
    source_id: str,
    workspace_id: str,
    actor_id: str,
    reason: str,
    now: datetime | None = None,
) -> ManagementSource:
    source = _workspace_source(session, source_id=source_id, workspace_id=workspace_id)
    if not reason.strip():
        raise ValueError("REVOCATION_REASON_REQUIRED")
    before = source.authorization_status
    source.authorization_status = "REVOKED"
    source.revoked_at = now or utc_now()
    source.revocation_reason = reason.strip()
    _audit(
        session,
        source=source,
        actor_id=actor_id,
        event_type="REVOKED",
        before_status=before,
        after_status="REVOKED",
        scopes=list(source.authorized_scopes_json),
        reason=source.revocation_reason,
    )
    return source


def _workspace_source(
    session: Session, *, source_id: str, workspace_id: str
) -> ManagementSource:
    source = session.get(ManagementSource, source_id)
    if source is None:
        raise ValueError("SOURCE_NOT_FOUND")
    if source.workspace_id != workspace_id:
        raise ValueError("CROSS_WORKSPACE_SOURCE_DENIED")
    return source


def _audit(
    session: Session,
    *,
    source: ManagementSource,
    actor_id: str,
    event_type: str,
    before_status: str | None,
    after_status: str,
    scopes: list[str],
    reason: str | None = None,
) -> None:
    if source.workspace_id is None:
        raise ValueError("WORKSPACE_REQUIRED")
    session.add(
        SourceAuthorizationAudit(
            source_id=source.id,
            workspace_id=source.workspace_id,
            actor_id=actor_id,
            event_type=event_type,
            before_status=before_status,
            after_status=after_status,
            scopes_json=scopes,
            reason=reason,
        )
    )
