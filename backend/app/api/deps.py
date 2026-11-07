"""FastAPI dependencies: access to the container and API-key authentication."""

from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException, Request, status

from app.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def require_api_key(
    x_api_key: str | None = Header(default=None, description="Merchant API key"),
    container: Container = Depends(get_container),
) -> None:
    expected = container.settings.merchant_api_key
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный или отсутствующий X-API-Key")
