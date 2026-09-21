from __future__ import annotations

import httpx

from app.ai.shadow import _classify_error


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_http_status_becomes_readable_code() -> None:
    assert _classify_error(_http_status_error(403)) == "HTTP_403"
    assert _classify_error(_http_status_error(400)) == "HTTP_400"
    assert _classify_error(_http_status_error(429)) == "HTTP_429"


def test_network_error_is_labelled() -> None:
    assert _classify_error(httpx.ConnectError("no route")) == "NETWORK_ConnectError"


def test_other_errors_keep_class_name() -> None:
    assert _classify_error(ValueError("bad json")) == "ValueError"
