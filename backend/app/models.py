"""Модель предметной области: счёт (Invoice), его статусы и бизнес-ошибки.

Здесь нет ни FastAPI, ни базы данных, ни блокчейна — только правила.
Счёт сам следит, в какой статус ему можно перейти (конечный автомат,
см. docs/05-state.md).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

WEI_PER_ETH = Decimal(10) ** 18  # 1 ETH = 10^18 wei


def eth_to_wei(amount_eth: Decimal) -> int:
    wei = Decimal(amount_eth) * WEI_PER_ETH
    if wei != wei.to_integral_value():
        raise ValueError("Сумма в ETH может иметь не более 18 знаков после запятой")
    return int(wei)


def wei_to_eth(wei: int) -> str:
    return format((Decimal(wei) / WEI_PER_ETH).normalize(), "f")


# ---------------------------------------------------------------- статусы
class InvoiceStatus(str, Enum):
    AWAITING_PAYMENT = "awaiting_payment"  # ждём оплату
    CONFIRMING = "confirming"              # транзакция есть, ждём подтверждений
    PAID = "paid"                          # оплачен
    EXPIRED = "expired"                    # истёк срок
    FAILED = "failed"                      # оплата не прошла


FINAL_STATUSES = {InvoiceStatus.PAID, InvoiceStatus.EXPIRED, InvoiceStatus.FAILED}


# ---------------------------------------------------------------- ошибки
class DomainError(Exception):
    """Ожидаемая ошибка, текст которой можно показать пользователю."""


class InvalidStateTransition(DomainError):
    def __init__(self, current: InvoiceStatus, target: InvoiceStatus):
        super().__init__(f"Нельзя перевести счёт из '{current.value}' в '{target.value}'")


class InvoiceNotFound(DomainError):
    def __init__(self, invoice_id: str):
        super().__init__(f"Счёт '{invoice_id}' не найден")


class InvoiceNotPayable(DomainError):
    def __init__(self, status: str):
        super().__init__(f"Счёт не ожидает оплаты (статус: {status})")


class TransactionAlreadyUsed(DomainError):
    def __init__(self, tx_hash: str):
        super().__init__(f"Транзакция {tx_hash} уже использована для другого счёта")


class InvalidTransactionHash(DomainError):
    def __init__(self, tx_hash: str):
        super().__init__(f"'{tx_hash}' — некорректный хэш транзакции")


class PaymentRejected(DomainError):
    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))


# ---------------------------------------------------------------- хронология
@dataclass(frozen=True)
class TimelineEntry:
    """Одна строка в хронологии счёта: «12:02:10 — Получена транзакция 0xabc…»."""

    invoice_id: str
    type: str       # например "invoice.created", "transaction.received", "invoice.paid"
    message: str    # понятный текст на русском
    created_at: datetime

    def to_dict(self) -> dict:
        return {"type": self.type, "message": self.message, "created_at": self.created_at.isoformat()}


# ---------------------------------------------------------------- счёт
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
    payer_address: str | None = None  # None = транзакция ещё не проверена
    tx_submitted_at: datetime | None = None
    confirmations: int = 0
    failure_reason: str | None = None
    paid_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def create(cls, *, amount_wei: int, recipient: str, chain_id: int, description: str,
               order_id: str | None, ttl: timedelta, now: datetime) -> "Invoice":
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

    # --- вопросы к счёту
    def is_final(self) -> bool:
        return self.status in FINAL_STATUSES

    def is_overdue(self, now: datetime) -> bool:
        return self.status is InvoiceStatus.AWAITING_PAYMENT and now >= self.expires_at

    # --- переходы между статусами
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

    # --- представление для JSON (API и вебхуки)
    def to_dict(self) -> dict:
        def iso(value):
            return value.isoformat() if value else None

        return {
            "id": self.id,
            "order_id": self.order_id,
            "description": self.description,
            "status": self.status.value,
            "amount_wei": str(self.amount_wei),
            "amount_eth": wei_to_eth(self.amount_wei),
            "recipient": self.recipient,
            "chain_id": self.chain_id,
            "tx_hash": self.tx_hash,
            "payer_address": self.payer_address,
            "confirmations": self.confirmations,
            "failure_reason": self.failure_reason,
            "created_at": iso(self.created_at),
            "expires_at": iso(self.expires_at),
            "paid_at": iso(self.paid_at),
        }
