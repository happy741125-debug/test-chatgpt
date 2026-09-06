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
