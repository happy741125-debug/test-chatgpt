from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import SourceRecord, SourceRecordAudit, SourceRecordEvidence, Workspace
from app.services.source_records import ingest_source_record, tombstone_source_record
from app.services.source_registry import authorize_source, register_source, revoke_source


def _active_source(session, *, workspace_slug: str = "huoda", retention: str = "90_DAYS"):
    workspace = Workspace(slug=workspace_slug, name=workspace_slug)
    session.add(workspace)
    session.flush()
    source = register_source(
        session,
        workspace_id=workspace.id,
        source_type="DOCUMENT",
        external_source_key=f"{workspace_slug}-docs",
        name="Documents",
        authority_scope="approved documents",
        actor_id="jacky",
        classification="CONFIDENTIAL",
        retention_policy=retention,
    ).source
    authorize_source(
        session,
        source_id=source.id,
        workspace_id=workspace.id,
        actor_id="jacky",
        scopes=["document:read"],
        now=datetime(2026, 11, 22, 8, 0, tzinfo=UTC),
    )
    session.flush()
    return workspace, source


def _ingest(session, workspace, source, *, key: str = "doc-1", sha: str = "a" * 64):
    return ingest_source_record(
        session,
        workspace_id=workspace.id,
        source_id=source.id,
        external_record_key=key,
        record_type="document",
        content_ref=f"object://fixtures/{key}",
        content_sha256=sha,
        classification="CONFIDENTIAL",
        actor_id="jacky",
        mime_type="text/markdown",
        received_at=datetime(2026, 11, 22, 9, 0, tzinfo=UTC),
    )


def test_ingest_creates_record_evidence_retention_and_audit(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace, source = _active_source(session)
        result = _ingest(session, workspace, source)
        session.flush()

        evidence = session.scalar(select(SourceRecordEvidence))
        audit = session.scalar(select(SourceRecordAudit))
        assert result.created is True
        assert result.record.workspace_id == workspace.id
        assert result.record.record_type == "DOCUMENT"
        assert result.record.retention_until == datetime(2027, 2, 20, 9, 0, tzinfo=UTC)
        assert result.record.authorization_version == "2026-11-22T08:00:00+00:00"
        assert evidence is not None and evidence.content_sha256 == "a" * 64
        assert audit is not None and audit.event_type == "INGESTED"


def test_same_external_record_and_hash_is_idempotent(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace, source = _active_source(session)
        first = _ingest(session, workspace, source)
        second = _ingest(session, workspace, source)

        assert first.created is True
        assert second.created is False
        assert second.record.id == first.record.id
        assert len(session.scalars(select(SourceRecord)).all()) == 1


def test_same_external_record_with_changed_content_is_conflict(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace, source = _active_source(session)
        _ingest(session, workspace, source, sha="a" * 64)

        with pytest.raises(ValueError, match="SOURCE_RECORD_CONFLICT"):
            _ingest(session, workspace, source, sha="b" * 64)


def test_revoked_source_cannot_ingest(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace, source = _active_source(session)
        revoke_source(
            session,
            source_id=source.id,
            workspace_id=workspace.id,
            actor_id="jacky",
            reason="authorization removed",
        )

        with pytest.raises(ValueError, match="SOURCE_NOT_AUTHORIZED"):
            _ingest(session, workspace, source)


def test_cross_workspace_and_classification_downgrade_are_denied(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace, source = _active_source(session)
        other = Workspace(slug="personal", name="personal")
        session.add(other)
        session.flush()

        with pytest.raises(ValueError, match="CROSS_WORKSPACE_SOURCE_DENIED"):
            ingest_source_record(
                session,
                workspace_id=other.id,
                source_id=source.id,
                external_record_key="doc-cross",
                record_type="DOCUMENT",
                content_ref="object://fixtures/cross",
                content_sha256="c" * 64,
                classification="CONFIDENTIAL",
                actor_id="jacky",
            )
        with pytest.raises(ValueError, match="CLASSIFICATION_DOWNGRADE_DENIED"):
            ingest_source_record(
                session,
                workspace_id=workspace.id,
                source_id=source.id,
                external_record_key="doc-low",
                record_type="DOCUMENT",
                content_ref="object://fixtures/low",
                content_sha256="d" * 64,
                classification="INTERNAL",
                actor_id="jacky",
            )


def test_tombstone_keeps_record_and_appends_audit(test_context) -> None:
    _, database, _ = test_context
    with database.session_factory() as session:
        workspace, source = _active_source(session, retention="SOURCE_CONTROLLED")
        record = _ingest(session, workspace, source).record
        tombstone_source_record(
            session,
            workspace_id=workspace.id,
            source_record_id=record.id,
            actor_id="jacky",
            reason="source deletion request",
            now=datetime(2026, 11, 22, 10, 0, tzinfo=UTC),
        )
        session.flush()

        audits = session.scalars(
            select(SourceRecordAudit).order_by(SourceRecordAudit.created_at)
        ).all()
        assert session.get(SourceRecord, record.id) is record
        assert record.processing_status == "TOMBSTONED"
        assert record.retention_until is None
        assert [audit.event_type for audit in audits] == ["INGESTED", "TOMBSTONED"]
