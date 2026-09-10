from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from app.security.password import verify_password


def _stored_password_hash(request: Request) -> str | None:
    from app.models import AdminCredential

    database = getattr(request.app.state, "database", None)
    if database is None:
        return None
    with database.session_factory() as session:
        credential = session.get(AdminCredential, "singleton")
        return credential.password_hash if credential is not None else None


def require_ops_access(
    request: Request,
    ops_token: Annotated[str | None, Header(alias="X-Ops-Token")] = None,
) -> None:
    expected = request.app.state.settings.ops_api_token
    stored_hash = _stored_password_hash(request)
    if not expected and not stored_hash:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_code": "OPS_API_NOT_CONFIGURED"},
        )
    if ops_token:
        # The env token stays valid as break-glass recovery; a changed password
        # is accepted in addition to it.
        if expected and hmac.compare_digest(ops_token, expected):
            return
        if stored_hash and verify_password(ops_token, stored_hash):
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error_code": "OPS_ACCESS_DENIED"},
    )


OpsAccess = Annotated[None, Depends(require_ops_access)]


def require_upload_access(
    request: Request,
    upload_token: Annotated[str | None, Header(alias="X-Upload-Token")] = None,
    ops_token: Annotated[str | None, Header(alias="X-Ops-Token")] = None,
) -> None:
    settings = request.app.state.settings
    if ops_token:
        stored_hash = _stored_password_hash(request)
        if settings.ops_api_token and hmac.compare_digest(ops_token, settings.ops_api_token):
            return
        if stored_hash and verify_password(ops_token, stored_hash):
            return
    expected = settings.upload_api_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_code": "UPLOAD_API_NOT_CONFIGURED"},
        )
    if not upload_token or not hmac.compare_digest(upload_token, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "UPLOAD_ACCESS_DENIED"},
        )


UploadAccess = Annotated[None, Depends(require_upload_access)]
