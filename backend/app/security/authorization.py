from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthorizationAudit, PermissionPolicy, WorkspaceMembership


class DataClassification(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


CLASSIFICATION_RANK = {
    DataClassification.PUBLIC.value: 0,
    DataClassification.INTERNAL.value: 1,
    DataClassification.CONFIDENTIAL.value: 2,
    DataClassification.RESTRICTED.value: 3,
}


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason_code: str


class WorkspaceAccessDenied(PermissionError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def authorize_workspace_action(
    session: Session,
    *,
    actor_id: str,
    workspace_id: str,
    resource: str,
    action: str,
    classification: str,
    resource_id: str | None = None,
    resource_workspace_id: str | None = None,
) -> AccessDecision:
    """Evaluate one action and append an audit row in the caller's transaction.

    Request parameters are never treated as proof of access. A current membership
    and an explicit ALLOW policy are both required; any matching DENY wins.
    """

    decision = _evaluate_workspace_action(
        session,
        actor_id=actor_id,
        workspace_id=workspace_id,
        resource=resource,
        action=action,
        classification=classification,
        resource_workspace_id=resource_workspace_id,
    )
    session.add(
        AuthorizationAudit(
            workspace_id=workspace_id,
            actor_id=actor_id,
            resource=resource,
            resource_id=resource_id,
            action=action,
            classification=classification,
            allowed=decision.allowed,
            reason_code=decision.reason_code,
        )
    )
    return decision


def require_workspace_action(
    session: Session,
    *,
    actor_id: str,
    workspace_id: str,
    resource: str,
    action: str,
    classification: str,
    resource_id: str | None = None,
    resource_workspace_id: str | None = None,
) -> None:
    decision = authorize_workspace_action(
        session,
        actor_id=actor_id,
        workspace_id=workspace_id,
        resource=resource,
        action=action,
        classification=classification,
        resource_id=resource_id,
        resource_workspace_id=resource_workspace_id,
    )
    if not decision.allowed:
        raise WorkspaceAccessDenied(decision.reason_code)


def _evaluate_workspace_action(
    session: Session,
    *,
    actor_id: str,
    workspace_id: str,
    resource: str,
    action: str,
    classification: str,
    resource_workspace_id: str | None,
) -> AccessDecision:
    requested_rank = CLASSIFICATION_RANK.get(classification)
    if requested_rank is None:
        return AccessDecision(False, "CLASSIFICATION_UNKNOWN")
    if resource_workspace_id is not None and resource_workspace_id != workspace_id:
        return AccessDecision(False, "CROSS_WORKSPACE_DENIED")

    membership = session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.actor_id == actor_id,
            WorkspaceMembership.status == "ACTIVE",
        )
    )
    if membership is None:
        return AccessDecision(False, "MEMBERSHIP_REQUIRED")

    membership_rank = CLASSIFICATION_RANK.get(membership.max_classification)
    if membership_rank is None or requested_rank > membership_rank:
        return AccessDecision(False, "CLASSIFICATION_DENIED")

    policies = session.scalars(
        select(PermissionPolicy).where(
            PermissionPolicy.workspace_id == workspace_id,
            PermissionPolicy.role == membership.role,
            PermissionPolicy.resource == resource,
            PermissionPolicy.action == action,
        )
    ).all()
    applicable = [
        policy
        for policy in policies
        if CLASSIFICATION_RANK.get(policy.max_classification, -1) >= requested_rank
    ]
    if any(policy.effect == "DENY" for policy in applicable):
        return AccessDecision(False, "EXPLICIT_DENY")
    if any(policy.effect == "ALLOW" for policy in applicable):
        return AccessDecision(True, "POLICY_ALLOWED")
    return AccessDecision(False, "POLICY_REQUIRED")
