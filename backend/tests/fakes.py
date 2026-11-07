"""Test doubles that implement the same ports as the real adapters (Liskov substitution)."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from app.domain.invoice import Invoice, InvoiceStatus
from app.ports.blockchain import BlockchainGateway, ChainReceipt, ChainTransaction
from app.ports.notifier import PaymentEvent, PaymentNotifier
from app.ports.repository import InvoiceRepository

MERCHANT = "0x1111111111111111111111111111111111111111"
PAYER = "0x2222222222222222222222222222222222222222"
SEPOLIA = 11155111


def tx_hash(n: int) -> str:
    return "0x" + f"{n:064x}"


class FakeClock:
    def __init__(self, start: datetime | None = None):
        self.now = start or datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


class FakeBlockchain(BlockchainGateway):
    def __init__(self, head: int = 100):
        self.head = head
        self.txs: dict[str, ChainTransaction] = {}
        self.receipts: dict[str, ChainReceipt] = {}

    def broadcast(self, h: str, *, to: str = MERCHANT, value: int, chain_id: int = SEPOLIA) -> None:
        self.txs[h] = ChainTransaction(h, PAYER, to, value, chain_id, None)

    def mine(self, h: str, *, success: bool = True) -> None:
        self.head += 1
        self.receipts[h] = ChainReceipt(success, self.head)

    def get_transaction(self, tx_hash: str) -> ChainTransaction | None:
        return self.txs.get(tx_hash)

    def get_receipt(self, tx_hash: str) -> ChainReceipt | None:
        return self.receipts.get(tx_hash)

    def get_block_number(self) -> int:
        return self.head


class InMemoryInvoiceRepository(InvoiceRepository):
    """Stores copies so tests catch a service that forgets to call update()."""

    def __init__(self):
        self.items: dict[str, Invoice] = {}

    def add(self, invoice: Invoice) -> None:
        self.items[invoice.id] = copy.deepcopy(invoice)

    def update(self, invoice: Invoice) -> None:
        self.items[invoice.id] = copy.deepcopy(invoice)

    def get(self, invoice_id: str) -> Invoice | None:
        item = self.items.get(invoice_id)
        return copy.deepcopy(item) if item else None

    def get_by_tx_hash(self, tx_hash: str) -> Invoice | None:
        return next((copy.deepcopy(i) for i in self.items.values() if i.tx_hash == tx_hash), None)

    def list_recent(self, limit: int = 50) -> list[Invoice]:
        return sorted(self.items.values(), key=lambda i: i.created_at, reverse=True)[:limit]

    def list_by_status(self, status: InvoiceStatus) -> list[Invoice]:
        return [copy.deepcopy(i) for i in self.items.values() if i.status is status]


class RecordingNotifier(PaymentNotifier):
    def __init__(self):
        self.events: list[PaymentEvent] = []

    def notify(self, event: PaymentEvent) -> None:
        self.events.append(event)

    @property
    def types(self) -> list[str]:
        return [e.type for e in self.events]
