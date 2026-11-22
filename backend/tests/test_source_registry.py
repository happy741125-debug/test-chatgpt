from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import ManagementSource, SourceAuthorizationAudit, Workspace
from app.services.source_registry import (
    authorize_source,
    register_source,
    revoke_source,
)


def _workspace(session, *, slug: str = "huoda") -> Workspace:
    workspace = Workspace(slug=slug, name=slug)
    session.add(workspace)
    session.flush()
    return workspace


def test_supported_source_types_register_with_workspace_governance(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace = _workspace(session)
        for source_type in ("LINE", "GMAIL", "DOCUMENT", "API", "CALENDAR", "MANUAL"):
            result = register_source(
                session,
                workspace_id=workspace.id,
                source_type=source_type,
                external_source_key=f"{source_type.lower()}-primary",
                name=f"{source_type} primary",
                authority_scope="已授權的唯讀來源",
                actor_id="jacky",
                classification="CONFIDENTIAL",
                retention_policy="90_DAYS",
                freshness_threshold_hours=24,
            )

            assert result.created is True
            assert result.source.workspace_id == workspace.id
            assert result.source.authorization_status == "PENDING"
            assert result.source.retention_policy == "90_DAYS"


def test_same_workspace_type_and_external_key_is_idempotent(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace = _workspace(session)
        first = register_source(
            session,
            workspace_id=workspace.id,
            source_type="GMAIL",
            external_source_key="owner@example.invalid",
            name="Owner mailbox",
            authority_scope="read only",
            actor_id="jacky",
        )
        second = register_source(
            session,
            workspace_id=workspace.id,
            source_type="gmail",
            external_source_key="owner@example.invalid",
            name="Ignored duplicate name",
            authority_scope="read only",
            actor_id="jacky",
        )

        assert first.created is True
        assert second.created is False
        assert second.source.id == first.source.id
        assert len(session.scalars(select(ManagementSource)).all()) == 1


def test_same_external_key_is_isolated_between_workspaces(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        huoda = _workspace(session, slug="huoda")
        personal = _workspace(session, slug="personal")

        first = register_source(
            session,
            workspace_id=huoda.id,
            source_type="LINE",
            external_source_key="line-user-1",
            name="貨達 LINE",
            authority_scope="read only",
            actor_id="jacky",
        )
        second = register_source(
            session,
            workspace_id=personal.id,
            source_type="LINE",
            external_source_key="line-user-1",
            name="個人 LINE",
            authority_scope="read only",
            actor_id="jacky",
        )

        assert first.source.id != second.source.id


def test_authorize_and_revoke_preserve_scopes_and_audit(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace = _workspace(session)
        source = register_source(
            session,
            workspace_id=workspace.id,
            source_type="API",
            external_source_key="gowarehouse-readonly",
            name="GoWarehouse read-only",
            authority_scope="approved read endpoints only",
            actor_id="jacky",
            retention_policy="REFERENCE_ONLY",
        ).source
        authorized_at = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
        authorize_source(
            session,
            source_id=source.id,
            workspace_id=workspace.id,
            actor_id="jacky",
            scopes=["orders:read", "inventory:read", "orders:read"],
            now=authorized_at,
        )
        revoke_source(
            session,
            source_id=source.id,
            workspace_id=workspace.id,
            actor_id="jacky",
            reason="user disconnected source",
            now=datetime(2026, 11, 22, 13, 0, tzinfo=UTC),
        )
        session.flush()

        audits = session.scalars(
            select(SourceAuthorizationAudit).order_by(SourceAuthorizationAudit.created_at)
        ).all()
        assert source.authorization_status == "REVOKED"
        assert source.authorized_at == authorized_at
        assert source.authorized_scopes_json == ["inventory:read", "orders:read"]
        assert source.revocation_reason == "user disconnected source"
        assert [audit.event_type for audit in audits] == [
            "REGISTERED",
            "AUTHORIZED",
            "REVOKED",
        ]


def test_cross_workspace_authorization_is_denied(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        huoda = _workspace(session, slug="huoda")
        personal = _workspace(session, slug="personal")
        source = register_source(
            session,
            workspace_id=huoda.id,
            source_type="DOCUMENT",
            external_source_key="strategy-v1",
            name="Strategy",
            authority_scope="reference",
            actor_id="jacky",
        ).source

        with pytest.raises(ValueError, match="CROSS_WORKSPACE_SOURCE_DENIED"):
            authorize_source(
                session,
                source_id=source.id,
                workspace_id=personal.id,
                actor_id="jacky",
                scopes=["document:read"],
            )


def test_invalid_workspace_type_classification_and_retention_are_rejected(
    test_context,
) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace = _workspace(session)
        common = {
            "session": session,
            "workspace_id": workspace.id,
            "external_source_key": "invalid",
            "name": "Invalid",
            "authority_scope": "none",
            "actor_id": "jacky",
        }

        with pytest.raises(ValueError, match="SOURCE_TYPE_NOT_ALLOWED"):
            register_source(source_type="UNKNOWN", **common)
        with pytest.raises(ValueError, match="CLASSIFICATION_UNKNOWN"):
            register_source(source_type="MANUAL", classification="SECRET", **common)
        with pytest.raises(ValueError, match="RETENTION_POLICY_NOT_ALLOWED"):
            register_source(source_type="MANUAL", retention_policy="FOREVER", **common)
