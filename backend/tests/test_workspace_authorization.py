from __future__ import annotations

from sqlalchemy import select

from app.models import (
    AuthorizationAudit,
    PermissionPolicy,
    Workspace,
    WorkspaceMembership,
)
from app.security.authorization import (
    WorkspaceAccessDenied,
    authorize_workspace_action,
    require_workspace_action,
)


def _workspace_access(session, *, max_classification: str = "RESTRICTED") -> Workspace:
    workspace = Workspace(slug="huoda", name="貨達")
    session.add(workspace)
    session.flush()
    session.add(
        WorkspaceMembership(
            workspace_id=workspace.id,
            actor_id="jacky",
            role="OWNER",
            max_classification=max_classification,
        )
    )
    session.add(
        PermissionPolicy(
            workspace_id=workspace.id,
            role="OWNER",
            resource="SOURCE_RECORD",
            action="READ",
            effect="ALLOW",
            max_classification="RESTRICTED",
        )
    )
    session.flush()
    return workspace


def test_explicit_policy_allows_workspace_member_and_writes_audit(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace = _workspace_access(session)

        decision = authorize_workspace_action(
            session,
            actor_id="jacky",
            workspace_id=workspace.id,
            resource="SOURCE_RECORD",
            action="READ",
            classification="CONFIDENTIAL",
            resource_id="record-1",
            resource_workspace_id=workspace.id,
        )
        session.flush()

        audit = session.scalar(select(AuthorizationAudit))
        assert decision.allowed is True
        assert decision.reason_code == "POLICY_ALLOWED"
        assert audit is not None
        assert audit.allowed is True
        assert audit.resource_id == "record-1"


def test_default_deny_without_membership_or_policy(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace = Workspace(slug="muguang", name="募光")
        session.add(workspace)
        session.flush()

        decision = authorize_workspace_action(
            session,
            actor_id="outsider",
            workspace_id=workspace.id,
            resource="SOURCE_RECORD",
            action="READ",
            classification="INTERNAL",
        )

        assert decision.allowed is False
        assert decision.reason_code == "MEMBERSHIP_REQUIRED"


def test_cross_workspace_resource_is_denied_even_for_owner(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace = _workspace_access(session)
        another = Workspace(slug="personal", name="個人")
        session.add(another)
        session.flush()

        decision = authorize_workspace_action(
            session,
            actor_id="jacky",
            workspace_id=workspace.id,
            resource="SOURCE_RECORD",
            action="READ",
            classification="INTERNAL",
            resource_workspace_id=another.id,
        )

        assert decision.allowed is False
        assert decision.reason_code == "CROSS_WORKSPACE_DENIED"


def test_membership_classification_ceiling_is_enforced(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace = _workspace_access(session, max_classification="INTERNAL")

        decision = authorize_workspace_action(
            session,
            actor_id="jacky",
            workspace_id=workspace.id,
            resource="SOURCE_RECORD",
            action="READ",
            classification="CONFIDENTIAL",
        )

        assert decision.allowed is False
        assert decision.reason_code == "CLASSIFICATION_DENIED"


def test_write_is_denied_when_only_read_policy_exists(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace = _workspace_access(session)

        decision = authorize_workspace_action(
            session,
            actor_id="jacky",
            workspace_id=workspace.id,
            resource="SOURCE_RECORD",
            action="WRITE",
            classification="INTERNAL",
        )

        assert decision.allowed is False
        assert decision.reason_code == "POLICY_REQUIRED"


def test_explicit_deny_wins_and_raise_helper_fails_closed(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace = _workspace_access(session)
        session.add(
            PermissionPolicy(
                workspace_id=workspace.id,
                role="OWNER",
                resource="SOURCE_RECORD",
                action="READ",
                effect="DENY",
                max_classification="RESTRICTED",
            )
        )
        session.flush()

        try:
            require_workspace_action(
                session,
                actor_id="jacky",
                workspace_id=workspace.id,
                resource="SOURCE_RECORD",
                action="READ",
                classification="INTERNAL",
            )
        except WorkspaceAccessDenied as exc:
            assert exc.reason_code == "EXPLICIT_DENY"
        else:
            raise AssertionError("Explicit DENY must fail closed")
