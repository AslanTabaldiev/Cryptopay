"""Бизнес-ошибки. Сервисы их выбрасывают, API-слой переводит в HTTP-коды."""


class DomainError(Exception):
    """Базовый класс для ожидаемых ошибок, которые показываются пользователю."""


class InvoiceNotFound(DomainError):
    def __init__(self, invoice_id: str):
        super().__init__(f"Счёт '{invoice_id}' не найден")


class TransactionAlreadyUsed(DomainError):
    def __init__(self, tx_hash: str):
        super().__init__(f"Транзакция {tx_hash} уже использована для другого счёта")


class InvoiceNotPayable(DomainError):
    def __init__(self, status: str):
        super().__init__(f"Счёт не ожидает оплаты (статус: {status})")


class PaymentRejected(DomainError):
    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class InvalidTransactionHash(DomainError):
    def __init__(self, tx_hash: str):
        super().__init__(f"'{tx_hash}' — некорректный хэш транзакции")
