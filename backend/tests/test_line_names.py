from __future__ import annotations

from datetime import UTC, datetime

from app.models import Channel, Identity, Message, Platform
from app.services.line_profile import LineProfileClient
from app.services.name_resolution import resolve_pending_line_names

OPS_HEADERS = {"X-Ops-Token": "test-ops-token"}


def test_group_endpoint_and_auth_header() -> None:
    seen: dict[str, str] = {}

    def transport(url: str, headers: dict[str, str]) -> dict[str, str]:
        seen["url"] = url
        seen["auth"] = headers.get("Authorization", "")
        return {"displayName": "王小明"}

    client = LineProfileClient("tok-123", transport=transport)
    assert client.fetch_display_name("group", "Ggroup", "Uuser") == "王小明"
    assert seen["url"].endswith("/group/Ggroup/member/Uuser")
    assert seen["auth"] == "Bearer tok-123"


def test_unknown_channel_type_and_failures_return_none() -> None:
    ok = LineProfileClient("tok", transport=lambda url, headers: {"displayName": "x"})
    assert ok.fetch_display_name("weird", "x", "y") is None  # unsupported source type

    no_token = LineProfileClient("", transport=lambda url, headers: {"displayName": "x"})
    assert no_token.fetch_display_name("group", "g", "u") is None

    failed = LineProfileClient("tok", transport=lambda url, headers: None)
    assert failed.fetch_display_name("group", "g", "u") is None

    blank_name = LineProfileClient("tok", transport=lambda url, headers: {"displayName": "  "})
    assert blank_name.fetch_display_name("group", "g", "u") is None


def _seed_nameless_line_member(database) -> None:  # type: ignore[no-untyped-def]
    now = datetime(2026, 9, 21, 4, 0, tzinfo=UTC)
    with database.session_factory() as session:
        session.add(
            Channel(
                id="ch-g1",
                platform=Platform.LINE.value,
                external_channel_id="Ggroup1",
                channel_type="group",
            )
        )
        session.add(
            Identity(
                id="idn-x",
                platform=Platform.LINE.value,
                external_identity_id="Uuser1",
            )
        )
        session.add(
            Message(
                id="m-x",
                platform=Platform.LINE.value,
                external_message_id="ext-x",
                raw_event_id="raw-x",
                channel_id="ch-g1",
                conversation_id="conv-x",
                message_type="text",
                text="缺貨了",
                source_created_at=now,
                sender_identity_id="idn-x",
            )
        )
        session.commit()


def test_resolve_pending_line_names_stores_real_name(test_context) -> None:
    _, database, _ = test_context
    _seed_nameless_line_member(database)

    def transport(url: str, headers: dict[str, str]) -> dict[str, str] | None:
        if url.endswith("/group/Ggroup1/member/Uuser1"):
            return {"displayName": "陳老闆"}
        return None

    client = LineProfileClient("tok", transport=transport)
    with database.session_factory() as session:
        result = resolve_pending_line_names(session, client)
    assert result == {"found": 1, "checked": 1, "resolved": 1}

    with database.session_factory() as session:
        identity = session.get(Identity, "idn-x")
        assert identity.display_name == "陳老闆"


def test_resolve_keeps_none_when_line_cannot_resolve(test_context) -> None:
    _, database, _ = test_context
    _seed_nameless_line_member(database)
    client = LineProfileClient("tok", transport=lambda url, headers: None)
    with database.session_factory() as session:
        result = resolve_pending_line_names(session, client)
    assert result == {"found": 1, "checked": 1, "resolved": 0}
    with database.session_factory() as session:
        assert session.get(Identity, "idn-x").display_name is None


def test_resolve_endpoint_requires_token_and_ops(test_context) -> None:
    client, _, _ = test_context
    # No LINE access token configured in tests -> clear 400, not a crash.
    missing = client.post("/api/admin/resolve-line-names", headers=OPS_HEADERS)
    assert missing.status_code == 400
    assert missing.json()["detail"]["error_code"] == "LINE_TOKEN_MISSING"
    # Requires ops access.
    assert client.post("/api/admin/resolve-line-names").status_code == 403
