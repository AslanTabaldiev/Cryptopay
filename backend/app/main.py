"""FastAPI application factory.

Run locally:  uvicorn app.main:create_app --factory --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.routes import router
from app.config import Settings
from app.container import Container
from app.domain.errors import (
    DomainError,
    InvalidTransactionHash,
    InvoiceNotFound,
    InvoiceNotPayable,
    PaymentRejected,
    TransactionAlreadyUsed,
)
from app.domain.invoice import InvalidStateTransition
from app.ports.blockchain import BlockchainError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ERROR_STATUS: dict[type[Exception], int] = {
    InvoiceNotFound: 404,
    InvoiceNotPayable: 409,
    TransactionAlreadyUsed: 409,
    InvalidStateTransition: 409,
    PaymentRejected: 422,
    InvalidTransactionHash: 422,
    ValueError: 422,
    BlockchainError: 503,
}


def create_app(container: Container | None = None) -> FastAPI:
    container = container or Container.build(Settings.from_env())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if container.settings.run_watcher:
            container.watcher.start()
        yield
        await container.watcher.stop()

    app = FastAPI(
        title="CryptoPay Gateway",
        version="1.0.0",
        description="Приём платежей в ETH (сеть Sepolia) через кошелёк MetaMask.",
        lifespan=lifespan,
    )
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=container.settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

    async def handle_error(_: Request, exc: Exception) -> JSONResponse:
        code = next((c for t, c in ERROR_STATUS.items() if isinstance(exc, t)), 400)
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    for exc_type in (DomainError, InvalidStateTransition, BlockchainError, ValueError):
        app.add_exception_handler(exc_type, handle_error)

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(router)
    _mount_frontend(app, container.settings.static_dir)
    return app


def _mount_frontend(app: FastAPI, static_dir: str | None) -> None:
    """Отдаёт собранный React-сайт тем же сервисом: один URL, без CORS.

    Маршруты /api, /docs и /health зарегистрированы раньше и имеют приоритет;
    всё остальное — файлы сайта, а неизвестные пути отдают index.html
    (клиентский роутинг React для /pay/:id и /dashboard).
    """
    if not static_dir or not (Path(static_dir) / "index.html").exists():

        @app.get("/", include_in_schema=False)
        def root() -> dict:
            return {"service": "CryptoPay Gateway", "docs": "/docs"}

        return

    root_dir = Path(static_dir).resolve()
    index = root_dir / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        candidate = (root_dir / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root_dir):
            return FileResponse(candidate)
        return FileResponse(index)
