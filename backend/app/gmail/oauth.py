from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GmailTokens:
    access_token: str
    refresh_token: str | None
    scope: str


@dataclass(frozen=True)
class GmailProfile:
    email_address: str
    history_id: str


def build_authorization_url(*, client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_READONLY_SCOPE,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


class GmailOAuthClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        http: httpx.Client | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.http = http

    def exchange_code(self, code: str) -> GmailTokens:
        return self._token_request(
            {
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            }
        )

    def refresh_access_token(self, refresh_token: str) -> str:
        tokens = self._token_request(
            {
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
            }
        )
        return tokens.access_token

    def _token_request(self, data: dict[str, str]) -> GmailTokens:
        response = self._request("POST", GOOGLE_TOKEN_URL, data=data)
        payload = _json_object(response)
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise GmailAPIError("Google did not return an access token")
        refresh_token = payload.get("refresh_token")
        return GmailTokens(
            access_token=access_token,
            refresh_token=refresh_token if isinstance(refresh_token, str) else None,
            scope=str(payload.get("scope") or GMAIL_READONLY_SCOPE),
        )

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            if self.http is not None:
                response = self.http.request(method, url, **kwargs)
            else:
                with httpx.Client(timeout=30) as client:
                    response = client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            raise GmailAPIError(
                "Google authorization request failed",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise GmailAPIError("Google authorization service is unavailable") from exc


class GmailAPIClient:
    def __init__(self, access_token: str, *, http: httpx.Client | None = None) -> None:
        self.headers = {"Authorization": f"Bearer {access_token}"}
        self.http = http

    def get_profile(self) -> GmailProfile:
        payload = self._get_json(f"{GMAIL_API_BASE}/profile")
        email_address = payload.get("emailAddress")
        history_id = payload.get("historyId")
        if not isinstance(email_address, str) or not isinstance(history_id, str):
            raise GmailAPIError("Google mailbox profile response is incomplete")
        return GmailProfile(email_address=email_address.lower(), history_id=history_id)

    def list_recent_message_ids(self, *, days: int, limit: int) -> list[str]:
        return self._list_message_ids(
            f"{GMAIL_API_BASE}/messages",
            params={"q": f"newer_than:{days}d -in:spam -in:trash", "maxResults": limit},
            limit=limit,
            extract=_message_ids,
        )

    def list_history_message_ids(self, *, start_history_id: str, limit: int) -> list[str]:
        return self._list_message_ids(
            f"{GMAIL_API_BASE}/history",
            params={
                "startHistoryId": start_history_id,
                "historyTypes": "messageAdded",
                "maxResults": min(limit, 500),
            },
            limit=limit,
            extract=_history_message_ids,
        )

    def get_message(self, message_id: str) -> dict[str, Any]:
        return self._get_json(
            f"{GMAIL_API_BASE}/messages/{message_id}",
            params={"format": "full"},
        )

    def _list_message_ids(
        self,
        url: str,
        *,
        params: dict[str, str | int],
        limit: int,
        extract,
    ) -> list[str]:  # type: ignore[no-untyped-def]
        ids: list[str] = []
        page_token: str | None = None
        while len(ids) < limit:
            page_params = dict(params)
            if page_token:
                page_params["pageToken"] = page_token
            payload = self._get_json(url, params=page_params)
            ids.extend(extract(payload))
            next_token = payload.get("nextPageToken")
            if not isinstance(next_token, str) or not next_token:
                break
            page_token = next_token
        return list(dict.fromkeys(ids))[:limit]

    def _get_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            if self.http is not None:
                response = self.http.get(url, headers=self.headers, **kwargs)
            else:
                with httpx.Client(timeout=30) as client:
                    response = client.get(url, headers=self.headers, **kwargs)
            response.raise_for_status()
            return _json_object(response)
        except httpx.HTTPStatusError as exc:
            raise GmailAPIError(
                "Gmail request failed",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise GmailAPIError("Gmail service is unavailable") from exc


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise GmailAPIError("Google returned an unreadable response") from exc
    if not isinstance(payload, dict):
        raise GmailAPIError("Google returned an unexpected response")
    return payload


def _message_ids(payload: dict[str, Any]) -> list[str]:
    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        return []
    return [
        item["id"]
        for item in messages
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]


def _history_message_ids(payload: dict[str, Any]) -> list[str]:
    result: list[str] = []
    history = payload.get("history", [])
    if not isinstance(history, list):
        return result
    for record in history:
        if not isinstance(record, dict):
            continue
        added = record.get("messagesAdded", [])
        if not isinstance(added, list):
            continue
        for item in added:
            message = item.get("message") if isinstance(item, dict) else None
            if isinstance(message, dict) and isinstance(message.get("id"), str):
                result.append(message["id"])
    return result
