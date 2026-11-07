"""Сущность «Счёт» (Invoice) и её конечный автомат (см. docs/05-state.md).

Чистый Python: без FastAPI, SQLAlchemy и кода блокчейна. Сама сущность
контролирует, какие переходы между статусами разрешены.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class InvoiceStatus(str, Enum):
    AWAITING_PAYMENT = "awaiting_payment"
    CONFIRMING = "confirming"
    PAID = "paid"
    EXPIRED = "expired"
    FAILED = "failed"


FINAL_STATUSES = frozenset({InvoiceStatus.PAID, InvoiceStatus.EXPIRED, InvoiceStatus.FAILED})


class InvalidStateTransition(Exception):
    def __init__(self, current: InvoiceStatus, target: InvoiceStatus):
        super().__init__(f"Нельзя перевести счёт из '{current.value}' в '{target.value}'")
        self.current = current
        self.target = target


@dataclass
class Invoice:
    id: str
    amount_wei: int
    recipient: str
    chain_id: int
    description: str
    order_id: str | None
    status: InvoiceStatus
    created_at: datetime
    expires_at: datetime
    tx_hash: str | None = None
    payer_address: str | None = None
    tx_submitted_at: datetime | None = None
    confirmations: int = 0
    failure_reason: str | None = None
    paid_at: datetime | None = None
    updated_at: datetime | None = None

    # ---------- factory ----------
    @classmethod
    def create(
        cls,
        *,
        amount_wei: int,
        recipient: str,
        chain_id: int,
        description: str,
        order_id: str | None,
        ttl: timedelta,
        now: datetime,
    ) -> "Invoice":
        if amount_wei <= 0:
            raise ValueError("Сумма должна быть больше нуля")
        return cls(
            id=uuid.uuid4().hex,
            amount_wei=amount_wei,
            recipient=recipient.lower(),
            chain_id=chain_id,
            description=description,
            order_id=order_id,
            status=InvoiceStatus.AWAITING_PAYMENT,
            created_at=now,
            expires_at=now + ttl,
            updated_at=now,
        )

    # ---------- queries ----------
    def is_final(self) -> bool:
        return self.status in FINAL_STATUSES

    def is_overdue(self, now: datetime) -> bool:
        return self.status is InvoiceStatus.AWAITING_PAYMENT and now >= self.expires_at

    # ---------- transitions ----------
    def _move(self, target: InvoiceStatus, allowed_from: set[InvoiceStatus], now: datetime) -> None:
        if self.status not in allowed_from:
            raise InvalidStateTransition(self.status, target)
        self.status = target
        self.updated_at = now

    def attach_transaction(self, tx_hash: str, payer: str | None, now: datetime) -> None:
        self._move(InvoiceStatus.CONFIRMING, {InvoiceStatus.AWAITING_PAYMENT}, now)
        self.tx_hash = tx_hash.lower()
        self.payer_address = payer.lower() if payer else None
        self.tx_submitted_at = now

    def update_confirmations(self, confirmations: int, now: datetime) -> None:
        if self.status is not InvoiceStatus.CONFIRMING:
            raise InvalidStateTransition(self.status, InvoiceStatus.CONFIRMING)
        self.confirmations = max(0, confirmations)
        self.updated_at = now

    def mark_paid(self, now: datetime) -> None:
        self._move(InvoiceStatus.PAID, {InvoiceStatus.CONFIRMING}, now)
        self.paid_at = now

    def mark_failed(self, reason: str, now: datetime) -> None:
        self._move(InvoiceStatus.FAILED, {InvoiceStatus.CONFIRMING}, now)
        self.failure_reason = reason

    def expire(self, now: datetime) -> None:
        self._move(InvoiceStatus.EXPIRED, {InvoiceStatus.AWAITING_PAYMENT}, now)
