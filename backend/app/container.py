"""Composition root: the only place that knows concrete adapter classes.

Services receive their dependencies through constructors (Dependency Inversion).
Swapping Ethereum for another chain, or SQL for another store, means changing
this file only.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters.ethereum_rpc import EthereumJsonRpcGateway
from app.adapters.notifiers import CompositeNotifier, LoggingNotifier, WebhookNotifier
from app.adapters.sql_repository import SqlAlchemyInvoiceRepository, create_db_engine
from app.config import Settings
from app.ports.blockchain import BlockchainGateway
from app.ports.notifier import PaymentNotifier
from app.ports.repository import InvoiceRepository
from app.services.invoice_service import InvoiceService
from app.services.payment_service import PaymentService
from app.services.validation import PaymentValidator
from app.workers.payment_watcher import PaymentWatcher


@dataclass
class Container:
    settings: Settings
    invoice_service: InvoiceService
    payment_service: PaymentService
    watcher: PaymentWatcher

    @classmethod
    def build(
        cls,
        settings: Settings,
        *,
        repo: InvoiceRepository | None = None,
        chain: BlockchainGateway | None = None,
        notifier: PaymentNotifier | None = None,
    ) -> "Container":
        repo = repo or SqlAlchemyInvoiceRepository(create_db_engine(settings.database_url))
        chain = chain or EthereumJsonRpcGateway(settings.rpc_url)
        if notifier is None:
            notifiers: list[PaymentNotifier] = [LoggingNotifier()]
            if settings.webhook_url:
                notifiers.append(WebhookNotifier(settings.webhook_url, settings.webhook_secret))
            notifier = CompositeNotifier(notifiers)

        invoice_service = InvoiceService(
            repo,
            notifier,
            recipient=settings.merchant_address,
            chain_id=settings.chain_id,
            default_ttl_minutes=settings.default_ttl_minutes,
        )
        payment_service = PaymentService(
            repo,
            chain,
            PaymentValidator.default(),
            notifier,
            required_confirmations=settings.required_confirmations,
            tx_not_found_timeout_minutes=settings.tx_not_found_timeout_minutes,
        )
        watcher = PaymentWatcher(invoice_service, payment_service, settings.poll_interval_seconds)
        return cls(settings, invoice_service, payment_service, watcher)
