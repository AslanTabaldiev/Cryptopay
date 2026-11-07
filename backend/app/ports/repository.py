"""Port: persistence of invoices."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.invoice import Invoice, InvoiceStatus


class InvoiceRepository(ABC):
    @abstractmethod
    def add(self, invoice: Invoice) -> None: ...

    @abstractmethod
    def update(self, invoice: Invoice) -> None: ...

    @abstractmethod
    def get(self, invoice_id: str) -> Invoice | None: ...

    @abstractmethod
    def get_by_tx_hash(self, tx_hash: str) -> Invoice | None: ...

    @abstractmethod
    def list_recent(self, limit: int = 50) -> list[Invoice]: ...

    @abstractmethod
    def list_by_status(self, status: InvoiceStatus) -> list[Invoice]: ...
