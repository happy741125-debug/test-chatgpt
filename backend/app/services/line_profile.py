from __future__ import annotations

from collections.abc import Callable
from typing import Any

LINE_API_BASE = "https://api.line.me/v2/bot"

# invoke(url, headers) -> parsed LINE JSON response, or None on any failure.
# Injectable so tests never touch the network.
Transport = Callable[[str, dict[str, str]], dict[str, Any] | None]


class LineProfileClient:
    """Resolves a LINE userId to a display name via the Messaging API.

    Uses the group/room member-profile endpoints (which work for members of a
    group/room the bot is in, even non-friends) and falls back to the 1:1 profile
    endpoint. Any failure returns None so callers keep their de-identified label.
    """

    def __init__(
        self,
        access_token: str,
        *,
        transport: Transport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._token = access_token
        self._timeout = timeout
        self._get = transport or self._http_get

    def fetch_display_name(
        self,
        channel_type: str,
        conversation_external_id: str,
        user_external_id: str,
    ) -> str | None:
        if not self._token or not user_external_id:
            return None
        url = self._endpoint(channel_type, conversation_external_id, user_external_id)
        if url is None:
            return None
        payload = self._get(url, {"Authorization": f"Bearer {self._token}"})
        if not isinstance(payload, dict):
            return None
        name = payload.get("displayName")
        return name if isinstance(name, str) and name.strip() else None

    def _endpoint(
        self,
        channel_type: str,
        conversation_external_id: str,
        user_external_id: str,
    ) -> str | None:
        if channel_type == "group":
            return f"{LINE_API_BASE}/group/{conversation_external_id}/member/{user_external_id}"
        if channel_type == "room":
            return f"{LINE_API_BASE}/room/{conversation_external_id}/member/{user_external_id}"
        if channel_type == "user":
            return f"{LINE_API_BASE}/profile/{user_external_id}"
        return None

    def _http_get(self, url: str, headers: dict[str, str]) -> dict[str, Any] | None:
        import httpx

        try:
            response = httpx.get(url, headers=headers, timeout=self._timeout)
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        return data if isinstance(data, dict) else None
