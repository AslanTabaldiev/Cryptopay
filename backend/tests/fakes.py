"""Заменители для тестов. Реализуют те же интерфейсы, что и настоящие классы (принцип Лисков)."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from app.blockchain import BlockchainGateway, ChainReceipt, ChainTransaction
from app.database import InvoiceRepository, TimelineRepository
from app.models import Invoice, InvoiceStatus, TimelineEntry
from app.notifications import PaymentEvent, PaymentNotifier

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

    @property
    def final_types(self) -> list[str]:
        """Только окончательные события — те, что уходят магазину вебхуком."""
        return [e.type for e in self.events if e.is_final]


class InMemoryTimelineRepository(TimelineRepository):
    def __init__(self):
        self.entries: list[TimelineEntry] = []

    def add(self, entry: TimelineEntry) -> None:
        self.entries.append(entry)

    def list_for(self, invoice_id: str) -> list[TimelineEntry]:
        return [e for e in self.entries if e.invoice_id == invoice_id]


def _in_memory_shop():
    from app.shop import ShopOrder, ShopRepository

    class InMemoryShopRepository(ShopRepository):
        def __init__(self):
            self.items: dict[str, ShopOrder] = {}

        def add(self, order):
            self.items[order.id] = copy.deepcopy(order)

        def update(self, order):
            self.items[order.id] = copy.deepcopy(order)

        def get(self, order_id):
            return copy.deepcopy(self.items.get(order_id))

        def get_by_invoice(self, invoice_id):
            return next((copy.deepcopy(o) for o in self.items.values() if o.invoice_id == invoice_id), None)

        def list_recent(self, limit=20):
            return sorted(self.items.values(), key=lambda o: o.created_at, reverse=True)[:limit]

    return InMemoryShopRepository()


def make_client(repo: InvoiceRepository | None = None, engine=None, **settings_overrides):
    """Приложение FastAPI с фейковым блокчейном (и по умолчанию с хранилищем в памяти).

    Возвращает (client, chain, notifier, services).
    """
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import Services, create_app

    defaults = {"merchant_address": MERCHANT, "run_watcher": False, "required_confirmations": 1}
    settings = Settings(**{**defaults, **settings_overrides})
    chain, notifier = FakeBlockchain(), RecordingNotifier()
    if engine is not None:  # настоящая база SQLite для всех хранилищ
        from app.database import SqlInvoiceRepository, SqlTimelineRepository
        from app.shop import SqlShopRepository

        stores = dict(repo=SqlInvoiceRepository(engine), timeline=SqlTimelineRepository(engine),
                      shop_orders=SqlShopRepository(engine))
    else:
        stores = dict(repo=repo or InMemoryInvoiceRepository(), timeline=InMemoryTimelineRepository(),
                      shop_orders=_in_memory_shop())
    services = Services.build(settings, chain=chain, notifier=notifier, **stores)
    return TestClient(create_app(services)), chain, notifier, services
