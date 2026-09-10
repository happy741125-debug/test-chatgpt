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


def test_cors_uses_configured_dashboard_url(test_context) -> None:
    client, _, _ = test_context

    response = client.options(
        "/api/dashboard/today",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-ops-token",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


def test_release_identifies_v35_product_mapping(test_context) -> None:
    client, _, _ = test_context

    response = client.get("/health/release")

    assert response.status_code == 200
    assert response.json() == {
        "release": "2026.09.11-v3.5-product-mapping"
    }
