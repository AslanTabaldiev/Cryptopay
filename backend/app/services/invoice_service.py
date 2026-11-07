"""Use cases around the invoice itself: create, read, expire."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.domain.errors import InvoiceNotFound
from app.domain.invoice import Invoice, InvoiceStatus
from app.ports.notifier import PaymentEvent, PaymentNotifier
from app.ports.repository import InvoiceRepository
from app.serialization import WEI_PER_ETH
from app.services.clock import Clock, utc_now


def eth_to_wei(amount_eth: Decimal) -> int:
    wei = Decimal(amount_eth) * WEI_PER_ETH
    if wei != wei.to_integral_value():
        raise ValueError("Сумма в ETH может иметь не более 18 знаков после запятой")
    return int(wei)


class InvoiceService:
    def __init__(
        self,
        repo: InvoiceRepository,
        notifier: PaymentNotifier,
        *,
        recipient: str,
        chain_id: int,
        default_ttl_minutes: int,
        clock: Clock = utc_now,
    ):
        self._repo = repo
        self._notifier = notifier
        self._recipient = recipient
        self._chain_id = chain_id
        self._default_ttl = timedelta(minutes=default_ttl_minutes)
        self._clock = clock

    def create_invoice(
        self,
        amount_eth: Decimal,
        description: str,
        order_id: str | None = None,
        ttl_minutes: int | None = None,
    ) -> Invoice:
        invoice = Invoice.create(
            amount_wei=eth_to_wei(amount_eth),
            recipient=self._recipient,
            chain_id=self._chain_id,
            description=description,
            order_id=order_id,
            ttl=timedelta(minutes=ttl_minutes) if ttl_minutes else self._default_ttl,
            now=self._clock(),
        )
        self._repo.add(invoice)
        return invoice

    def get_invoice(self, invoice_id: str) -> Invoice:
        invoice = self._repo.get(invoice_id)
        if invoice is None:
            raise InvoiceNotFound(invoice_id)
        # Expire lazily too, so the status is correct even if the watcher was asleep.
        self._expire_if_overdue(invoice)
        return invoice

    def list_invoices(self, limit: int = 50) -> list[Invoice]:
        return self._repo.list_recent(limit)

    def expire_overdue(self) -> int:
        expired = 0
        for invoice in self._repo.list_by_status(InvoiceStatus.AWAITING_PAYMENT):
            expired += self._expire_if_overdue(invoice)
        return expired

    def _expire_if_overdue(self, invoice: Invoice) -> bool:
        now = self._clock()
        if not invoice.is_overdue(now):
            return False
        invoice.expire(now)
        self._repo.update(invoice)
        self._notifier.notify(PaymentEvent("invoice.expired", invoice, now))
        return True
