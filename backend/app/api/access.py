from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status


def require_ops_access(
    request: Request,
    ops_token: Annotated[str | None, Header(alias="X-Ops-Token")] = None,
) -> None:
    expected = request.app.state.settings.ops_api_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_code": "OPS_API_NOT_CONFIGURED"},
        )
    if not ops_token or not hmac.compare_digest(ops_token, expected):
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
    if (
        ops_token
        and settings.ops_api_token
        and hmac.compare_digest(ops_token, settings.ops_api_token)
    ):
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
