from __future__ import annotations


def test_liveness_and_readiness(test_context) -> None:
    client, _, _ = test_context

    live = client.get("/health/live")
    ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "checks": {"database": True, "queue": True},
    }


def test_request_has_correlation_id(test_context) -> None:
    client, _, _ = test_context

    response = client.get("/health/live", headers={"X-Request-ID": "test-request-id"})

    assert response.headers["X-Request-ID"] == "test-request-id"


def test_release_identifies_deployed_ai_foundation(test_context) -> None:
    client, _, _ = test_context

    response = client.get("/health/release")

    assert response.status_code == 200
    assert response.json() == {"release": "2026.09.07-operational-case-cards-v2"}
