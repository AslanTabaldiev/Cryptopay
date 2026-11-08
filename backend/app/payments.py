"""Бизнес-логика: создание счетов и проверка платежей.

  ValidationRule / PaymentValidator — правила проверки транзакции;
  InvoiceService — создать, найти, просрочить счёт;
  PaymentService — принять хэш транзакции и довести счёт до PAID/FAILED.

Сервисы получают зависимости через конструктор и знают только интерфейсы
(InvoiceRepository, BlockchainGateway, PaymentNotifier) — не конкретные
базу данных или ноду Ethereum.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from app.blockchain import BlockchainError, BlockchainGateway, ChainTransaction
from app.database import InvoiceRepository
from app.models import (
    InvalidTransactionHash,
    Invoice,
    InvoiceNotFound,
    InvoiceNotPayable,
    InvoiceStatus,
    PaymentRejected,
    TransactionAlreadyUsed,
    eth_to_wei,
    wei_to_eth,
)
from app.notifications import PaymentEvent, PaymentNotifier

log = logging.getLogger("cryptopay.payments")

Clock = Callable[[], datetime]  # функция «который час» — в тестах подменяется


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def short(value: str | None) -> str:
    """0xf3dFBBb4…8A8B → 0xf3df…8a8b — для коротких сообщений в хронологии."""
    return f"{value[:6]}…{value[-4:]}" if value else ""


# ================================================================ правила проверки
class ValidationRule(ABC):
    @abstractmethod
    def check(self, invoice: Invoice, tx: ChainTransaction) -> str | None:
        """Вернуть текст ошибки или None, если транзакция проходит правило."""


class ChainIdRule(ValidationRule):
    def check(self, invoice, tx):
        if tx.chain_id is not None and tx.chain_id != invoice.chain_id:
            return f"Неверная сеть: chain id {tx.chain_id}, ожидался {invoice.chain_id}"


class RecipientRule(ValidationRule):
    def check(self, invoice, tx):
        if (tx.to_address or "").lower() != invoice.recipient.lower():
            return f"Платёж отправлен на адрес {tx.to_address}, а ожидался {invoice.recipient}"


class AmountRule(ValidationRule):
    def check(self, invoice, tx):
        if tx.value_wei < invoice.amount_wei:
            return (f"Недостаточная сумма: получено {wei_to_eth(tx.value_wei)} ETH, "
                    f"ожидалось {wei_to_eth(invoice.amount_wei)} ETH")


class PaymentValidator:
    """Прогоняет транзакцию через все правила. Новое правило = новый класс, валидатор не меняется."""

    def __init__(self, rules: list[ValidationRule] | None = None):
        self.rules = rules if rules is not None else [ChainIdRule(), RecipientRule(), AmountRule()]

    def validate(self, invoice: Invoice, tx: ChainTransaction) -> list[str]:
        return [error for rule in self.rules if (error := rule.check(invoice, tx))]


# ================================================================ счета
class InvoiceService:
    def __init__(self, repo: InvoiceRepository, notifier: PaymentNotifier, *, recipient: str,
                 chain_id: int, default_ttl_minutes: int, clock: Clock = utc_now):
        self.repo = repo
        self.notifier = notifier
        self.recipient = recipient
        self.chain_id = chain_id
        self.default_ttl = timedelta(minutes=default_ttl_minutes)
        self.clock = clock

    def create_invoice(self, amount_eth: Decimal, description: str, order_id: str | None = None,
                       ttl_minutes: int | None = None) -> Invoice:
        invoice = Invoice.create(
            amount_wei=eth_to_wei(amount_eth),
            recipient=self.recipient,
            chain_id=self.chain_id,
            description=description,
            order_id=order_id,
            ttl=timedelta(minutes=ttl_minutes) if ttl_minutes else self.default_ttl,
            now=self.clock(),
        )
        self.repo.add(invoice)
        self.notifier.notify(PaymentEvent("invoice.created", invoice, invoice.created_at,
                                          f"Счёт создан на {wei_to_eth(invoice.amount_wei)} ETH"))
        return invoice

    def get_invoice(self, invoice_id: str) -> Invoice:
        invoice = self.repo.get(invoice_id)
        if invoice is None:
            raise InvoiceNotFound(invoice_id)
        self._expire_if_overdue(invoice)  # статус верный, даже если фоновая проверка ещё не дошла
        return invoice

    def list_invoices(self, limit: int = 50) -> list[Invoice]:
        return self.repo.list_recent(limit)

    def expire_overdue(self) -> int:
        """Вызывается фоновым процессом: просрочить все неоплаченные счета с истёкшим сроком."""
        return sum(self._expire_if_overdue(i) for i in self.repo.list_by_status(InvoiceStatus.AWAITING_PAYMENT))

    def _expire_if_overdue(self, invoice: Invoice) -> bool:
        now = self.clock()
        if not invoice.is_overdue(now):
            return False
        invoice.expire(now)
        self.repo.update(invoice)
        self.notifier.notify(PaymentEvent("invoice.expired", invoice, now, "Срок действия счёта истёк"))
        return True


# ================================================================ платежи
TX_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


class PaymentService:
    def __init__(self, repo: InvoiceRepository, chain: BlockchainGateway, validator: PaymentValidator,
                 notifier: PaymentNotifier, *, required_confirmations: int,
                 tx_not_found_timeout_minutes: int, clock: Clock = utc_now):
        self.repo = repo
        self.chain = chain
        self.validator = validator
        self.notifier = notifier
        self.required_confirmations = max(1, required_confirmations)
        self.not_found_timeout = timedelta(minutes=tx_not_found_timeout_minutes)
        self.clock = clock

    def submit_transaction(self, invoice_id: str, tx_hash: str) -> Invoice:
        """Покупатель оплатил в MetaMask, и страница прислала нам хэш транзакции."""
        tx_hash = tx_hash.strip().lower()
        if not TX_HASH_RE.match(tx_hash):
            raise InvalidTransactionHash(tx_hash)

        invoice = self.repo.get(invoice_id)
        if invoice is None:
            raise InvoiceNotFound(invoice_id)
        if invoice.tx_hash == tx_hash:
            return invoice  # повторный запрос с тем же хэшем — ничего не делаем

        now = self.clock()
        if invoice.is_overdue(now):
            invoice.expire(now)
            self.repo.update(invoice)
            self._notify("invoice.expired", invoice, "Срок действия счёта истёк")
        if invoice.status is not InvoiceStatus.AWAITING_PAYMENT:
            raise InvoiceNotPayable(invoice.status.value)
        if self.repo.get_by_tx_hash(tx_hash) is not None:
            raise TransactionAlreadyUsed(tx_hash)

        # Проверяем транзакцию в блокчейне. Если нода её ещё не видит (только что
        # отправлена) — принимаем, а проверим позже в refresh().
        tx = self.chain.get_transaction(tx_hash)
        if tx is not None:
            errors = self.validator.validate(invoice, tx)
            if errors:
                raise PaymentRejected(errors)

        invoice.attach_transaction(tx_hash, tx.from_address if tx else None, now)
        self.repo.update(invoice)
        if tx is not None:
            self._notify("transaction.received", invoice,
                         f"Получена транзакция {short(tx_hash)} от {short(tx.from_address)}. "
                         "Проверка пройдена: сеть, получатель и сумма верны")
        else:
            self._notify("transaction.received", invoice,
                         f"Получена транзакция {short(tx_hash)}. Нода её ещё не видит — проверим чуть позже")
        try:
            return self.refresh(invoice)
        except BlockchainError as exc:
            log.warning("Не удалось сразу обновить счёт %s: %s", invoice.id, exc)
            return invoice

    def refresh(self, invoice: Invoice) -> Invoice:
        """Посмотреть в блокчейн и продвинуть счёт в статусе CONFIRMING."""
        if invoice.status is not InvoiceStatus.CONFIRMING or not invoice.tx_hash:
            return invoice
        now = self.clock()

        if invoice.payer_address is None:  # транзакция ещё не проверялась
            tx = self.chain.get_transaction(invoice.tx_hash)
            if tx is None:
                if now - (invoice.tx_submitted_at or now) > self.not_found_timeout:
                    return self._fail(invoice, "Транзакция не найдена в сети")
                return invoice
            errors = self.validator.validate(invoice, tx)
            if errors:
                return self._fail(invoice, "; ".join(errors))
            invoice.payer_address = tx.from_address
            self.repo.update(invoice)
            self._notify("transaction.validated", invoice, "Транзакция появилась в сети и прошла проверку")

        receipt = self.chain.get_receipt(invoice.tx_hash)
        if receipt is None:
            return invoice  # ещё не в блоке
        if not receipt.success:
            return self._fail(invoice, "Транзакция отклонена сетью (reverted)")

        before = invoice.confirmations
        invoice.update_confirmations(self.chain.get_block_number() - receipt.block_number + 1, now)
        if invoice.confirmations != before:
            shown = min(invoice.confirmations, self.required_confirmations)
            self._notify("transaction.confirmation", invoice,
                         f"Блок #{receipt.block_number}: подтверждение {shown} из {self.required_confirmations}")
        if invoice.confirmations >= self.required_confirmations:
            invoice.mark_paid(now)
            self.repo.update(invoice)
            self._notify("invoice.paid", invoice, "Счёт оплачен — платёж уже нельзя отменить")
        elif invoice.confirmations != before:
            self.repo.update(invoice)
        return invoice

    def process_pending(self) -> int:
        """Вызывается фоновым процессом. Возвращает число счетов, получивших финальный статус."""
        finished = 0
        for invoice in self.repo.list_by_status(InvoiceStatus.CONFIRMING):
            try:
                finished += self.refresh(invoice).is_final()
            except BlockchainError as exc:
                log.warning("Не удалось обновить счёт %s: %s", invoice.id, exc)
        return finished

    def _fail(self, invoice: Invoice, reason: str) -> Invoice:
        invoice.mark_failed(reason, self.clock())
        self.repo.update(invoice)
        self._notify("invoice.failed", invoice, f"Оплата не прошла: {reason}")
        return invoice

    def _notify(self, event_type: str, invoice: Invoice, message: str) -> None:
        self.notifier.notify(PaymentEvent(event_type, invoice, self.clock(), message))
