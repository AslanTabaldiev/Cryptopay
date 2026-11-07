"""Port: telling the outside world that an invoice reached a final status."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.domain.invoice import Invoice


@dataclass(frozen=True)
class PaymentEvent:
    type: str  # "invoice.paid" | "invoice.failed" | "invoice.expired"
    invoice: Invoice
    occurred_at: datetime


class PaymentNotifier(ABC):
    @abstractmethod
    def notify(self, event: PaymentEvent) -> None:
        """Deliver the event. Implementations must not raise on delivery failure."""
