"""Правила проверки платежа.

Каждое правило — маленький класс с одной ответственностью. Новая проверка
(например, «плательщик в белом списке») добавляется новым классом-правилом,
который передаётся в PaymentValidator; существующий код не меняется
(принцип открытости/закрытости).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.invoice import Invoice
from app.ports.blockchain import ChainTransaction
from app.serialization import wei_to_eth


class ValidationRule(ABC):
    @abstractmethod
    def check(self, invoice: Invoice, tx: ChainTransaction) -> str | None:
        """Вернуть текст ошибки или None, если транзакция проходит правило."""


class RecipientRule(ValidationRule):
    def check(self, invoice: Invoice, tx: ChainTransaction) -> str | None:
        if (tx.to_address or "").lower() != invoice.recipient.lower():
            return f"Платёж отправлен на адрес {tx.to_address}, а ожидался {invoice.recipient}"
        return None


class AmountRule(ValidationRule):
    def check(self, invoice: Invoice, tx: ChainTransaction) -> str | None:
        if tx.value_wei < invoice.amount_wei:
            return (
                f"Недостаточная сумма: получено {wei_to_eth(tx.value_wei)} ETH, "
                f"ожидалось {wei_to_eth(invoice.amount_wei)} ETH"
            )
        return None


class ChainIdRule(ValidationRule):
    def check(self, invoice: Invoice, tx: ChainTransaction) -> str | None:
        if tx.chain_id is not None and tx.chain_id != invoice.chain_id:
            return f"Неверная сеть: chain id {tx.chain_id}, ожидался {invoice.chain_id}"
        return None


class PaymentValidator:
    def __init__(self, rules: list[ValidationRule]):
        self._rules = rules

    @classmethod
    def default(cls) -> "PaymentValidator":
        return cls([ChainIdRule(), RecipientRule(), AmountRule()])

    def validate(self, invoice: Invoice, tx: ChainTransaction) -> list[str]:
        return [error for rule in self._rules if (error := rule.check(invoice, tx))]
