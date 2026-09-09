from __future__ import annotations

OPS = {"X-Ops-Token": "test-ops-token"}
PROTECTED = "/api/gw-imports/summary"


def test_change_password_then_new_password_works(test_context) -> None:
    client, _, _ = test_context

    changed = client.post(
        "/api/admin/change-password",
        headers=OPS,
        json={"current_password": "test-ops-token", "new_password": "brandnew-pass-1"},
    )
    assert changed.status_code == 200
    assert changed.json()["ok"] is True

    # New password now authenticates.
    assert client.get(PROTECTED, headers={"X-Ops-Token": "brandnew-pass-1"}).status_code == 200
    # Env token still works as break-glass recovery.
    assert client.get(PROTECTED, headers=OPS).status_code == 200
    # A random wrong token is rejected.
    assert client.get(PROTECTED, headers={"X-Ops-Token": "nope"}).status_code == 403


def test_change_password_rejects_wrong_current(test_context) -> None:
    client, _, _ = test_context
    response = client.post(
        "/api/admin/change-password",
        headers=OPS,
        json={"current_password": "wrong", "new_password": "brandnew-pass-1"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "CURRENT_PASSWORD_INVALID"


def test_change_password_rejects_short_new(test_context) -> None:
    client, _, _ = test_context
    response = client.post(
        "/api/admin/change-password",
        headers=OPS,
        json={"current_password": "test-ops-token", "new_password": "123"},
    )
    assert response.status_code == 422


def test_change_password_requires_token(test_context) -> None:
    client, _, _ = test_context
    response = client.post(
        "/api/admin/change-password",
        json={"current_password": "test-ops-token", "new_password": "brandnew-pass-1"},
    )
    assert response.status_code == 403


def test_second_change_uses_updated_password(test_context) -> None:
    client, _, _ = test_context
    client.post(
        "/api/admin/change-password",
        headers=OPS,
        json={"current_password": "test-ops-token", "new_password": "first-pass-1"},
    )
    # Change again using the NEW password as current.
    second = client.post(
        "/api/admin/change-password",
        headers={"X-Ops-Token": "first-pass-1"},
        json={"current_password": "first-pass-1", "new_password": "second-pass-2"},
    )
    assert second.status_code == 200
    assert client.get(PROTECTED, headers={"X-Ops-Token": "second-pass-2"}).status_code == 200
