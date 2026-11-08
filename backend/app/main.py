"""Точка входа: собирает все части приложения вместе и запускает FastAPI.

Локальный запуск:  uvicorn app.main:create_app --factory --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api import ApiKeyGuard, describe_validation_errors, router
from app.blockchain import BlockchainError, BlockchainGateway, EthereumRpcGateway
from app.config import Settings
from app.database import InvoiceRepository, SqlInvoiceRepository, SqlTimelineRepository, TimelineRepository, make_engine
from app.models import DomainError, InvoiceNotFound, InvoiceNotPayable, InvalidStateTransition, TransactionAlreadyUsed
from app.notifications import (
    CompositeNotifier,
    LoggingNotifier,
    PaymentNotifier,
    TelegramNotifier,
    TimelineNotifier,
    WebhookNotifier,
)
from app.payments import InvoiceService, PaymentService, PaymentValidator
from app.shop import DemoShop, ShopRepository, SqlShopRepository
from app.shop import router as shop_router
from app.watcher import PaymentWatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@dataclass
class Services:
    """Все объекты приложения. Это единственное место, где выбираются конкретные классы
    (SQL, Ethereum, вебхук, Telegram). В тестах сюда передаются заменители."""

    settings: Settings
    invoices: InvoiceService
    payments: PaymentService
    watcher: PaymentWatcher
    guard: ApiKeyGuard
    timeline: TimelineRepository
    shop: DemoShop

    @classmethod
    def build(cls, settings: Settings, *, repo: InvoiceRepository | None = None,
              chain: BlockchainGateway | None = None, notifier: PaymentNotifier | None = None,
              timeline: TimelineRepository | None = None, shop_orders: ShopRepository | None = None) -> "Services":
        engine = make_engine(settings.database_url) if None in (repo, timeline, shop_orders) else None
        repo = repo or SqlInvoiceRepository(engine)
        timeline = timeline or SqlTimelineRepository(engine)
        shop_orders = shop_orders or SqlShopRepository(engine)
        chain = chain or EthereumRpcGateway(settings.rpc_url)

        # Кто узнаёт о событиях счёта (паттерн «Наблюдатель»).
        notifiers: list[PaymentNotifier] = [LoggingNotifier(), TimelineNotifier(timeline)]
        if notifier is not None:  # тесты подставляют свой
            notifiers.append(notifier)
        else:
            if settings.webhook_url:
                notifiers.append(WebhookNotifier(settings.webhook_url, settings.webhook_secret, timeline))
            if settings.telegram_bot_token and settings.telegram_chat_id:
                notifiers.append(TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id,
                                                  settings.explorer_url, timeline))
        notifier = CompositeNotifier(notifiers)

        invoices = InvoiceService(repo, notifier, recipient=settings.merchant_address,
                                  chain_id=settings.chain_id, default_ttl_minutes=settings.default_ttl_minutes)
        payments = PaymentService(repo, chain, PaymentValidator(), notifier,
                                  required_confirmations=settings.required_confirmations,
                                  tx_not_found_timeout_minutes=settings.tx_not_found_timeout_minutes)
        watcher = PaymentWatcher(invoices, payments, settings.poll_interval_seconds)
        guard = ApiKeyGuard(settings.api_key, settings.api_key_required)
        shop = DemoShop(shop_orders, invoices, settings.webhook_secret)
        return cls(settings, invoices, payments, watcher, guard, timeline, shop)


# Какой HTTP-код вернуть для какой ошибки (проверяются по порядку).
ERROR_CODES = {
    InvoiceNotFound: 404,
    InvoiceNotPayable: 409,
    TransactionAlreadyUsed: 409,
    InvalidStateTransition: 409,
    DomainError: 422,
    ValueError: 422,
}


def create_app(services: Services | None = None) -> FastAPI:
    services = services or Services.build(Settings.from_env())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if services.settings.run_watcher:
            services.watcher.start()
        yield
        await services.watcher.stop()

    app = FastAPI(title="CryptoPay Gateway", version="1.1.0", lifespan=lifespan,
                  description="Приём платежей в ETH (сеть Sepolia) через кошелёк MetaMask.")
    app.state.services = services
    app.add_middleware(CORSMiddleware, allow_origins=services.settings.cors_origins,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-API-Key"])

    # ---- ошибки → понятные JSON-ответы на русском
    async def domain_error(_: Request, exc: Exception):
        code = next(c for t, c in ERROR_CODES.items() if isinstance(exc, t))
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    async def blockchain_error(_: Request, exc: BlockchainError):
        logging.getLogger("cryptopay").warning("ошибка блокчейна: %s", exc)
        return JSONResponse(status_code=503,
                            content={"detail": "Сеть Ethereum временно недоступна. Попробуйте ещё раз через минуту."})

    async def validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": describe_validation_errors(exc.errors())})

    app.add_exception_handler(DomainError, domain_error)
    app.add_exception_handler(ValueError, domain_error)
    app.add_exception_handler(BlockchainError, blockchain_error)
    app.add_exception_handler(RequestValidationError, validation_error)

    @app.get("/health", tags=["Система"])
    def health():
        return {"status": "ok"}

    app.include_router(router)
    app.include_router(shop_router)
    serve_frontend(app, services.settings.static_dir)
    return app


def serve_frontend(app: FastAPI, static_dir: str | None) -> None:
    """Отдаёт собранный React-сайт тем же сервером, что и API (один адрес, без CORS).

    /api, /docs и /health зарегистрированы раньше, поэтому имеют приоритет.
    Неизвестные пути отдают index.html — их обрабатывает роутер React (/pay/:id, /dashboard).
    """
    if not static_dir or not (Path(static_dir) / "index.html").exists():
        @app.get("/", include_in_schema=False)
        def root():
            return {"service": "CryptoPay Gateway", "docs": "/docs"}
        return

    root_dir = Path(static_dir).resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        file = (root_dir / path).resolve()
        if path and file.is_file() and file.is_relative_to(root_dir):
            return FileResponse(file)
        return FileResponse(root_dir / "index.html")
