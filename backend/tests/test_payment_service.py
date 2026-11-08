from decimal import Decimal

import pytest

from app.models import (
    InvalidTransactionHash,
    InvoiceNotPayable,
    InvoiceStatus,
    PaymentRejected,
    TransactionAlreadyUsed,
    eth_to_wei,
)
from app.payments import InvoiceService, PaymentService, PaymentValidator, ValidationRule
from tests.fakes import (
    MERCHANT,
    FakeBlockchain,
    FakeClock,
    InMemoryInvoiceRepository,
    RecordingNotifier,
    tx_hash,
)

AMOUNT = eth_to_wei(Decimal("0.001"))


@pytest.fixture
def env():
    clock = FakeClock()
    repo = InMemoryInvoiceRepository()
    chain = FakeBlockchain()
    notifier = RecordingNotifier()
    invoices = InvoiceService(
        repo, notifier, recipient=MERCHANT, chain_id=11155111, default_ttl_minutes=15, clock=clock
    )
    payments = PaymentService(
        repo, chain, PaymentValidator(), notifier,
        required_confirmations=2, tx_not_found_timeout_minutes=10, clock=clock,
    )

    class Env:
        pass

    e = Env()
    e.clock, e.repo, e.chain, e.notifier, e.invoices, e.payments = clock, repo, chain, notifier, invoices, payments
    e.invoice = invoices.create_invoice(Decimal("0.001"), "Coffee")
    return e


def test_eth_to_wei():
    assert eth_to_wei(Decimal("1")) == 10**18
    assert eth_to_wei(Decimal("0.000000000000000001")) == 1
    with pytest.raises(ValueError):
        eth_to_wei(Decimal("0.0000000000000000001"))


def test_full_payment_flow(env):
    h = tx_hash(1)
    env.chain.broadcast(h, value=AMOUNT)

    invoice = env.payments.submit_transaction(env.invoice.id, h)
    assert invoice.status is InvoiceStatus.CONFIRMING

    env.chain.mine(h)  # 1 confirmation
    env.payments.process_pending()
    assert env.repo.get(env.invoice.id).confirmations == 1
    assert env.repo.get(env.invoice.id).status is InvoiceStatus.CONFIRMING

    env.chain.head += 1  # 2 confirmations
    env.payments.process_pending()
    paid = env.repo.get(env.invoice.id)
    assert paid.status is InvoiceStatus.PAID
    assert paid.paid_at is not None
    assert env.notifier.final_types == ["invoice.paid"]


def test_overpayment_is_accepted(env):
    h = tx_hash(2)
    env.chain.broadcast(h, value=AMOUNT * 2)
    assert env.payments.submit_transaction(env.invoice.id, h).status is InvoiceStatus.CONFIRMING


def test_underpayment_is_rejected(env):
    h = tx_hash(3)
    env.chain.broadcast(h, value=AMOUNT - 1)
    with pytest.raises(PaymentRejected, match="Недостаточная сумма"):
        env.payments.submit_transaction(env.invoice.id, h)
    assert env.repo.get(env.invoice.id).status is InvoiceStatus.AWAITING_PAYMENT


def test_wrong_recipient_is_rejected(env):
    h = tx_hash(4)
    env.chain.broadcast(h, to="0x9999999999999999999999999999999999999999", value=AMOUNT)
    with pytest.raises(PaymentRejected, match="ожидался"):
        env.payments.submit_transaction(env.invoice.id, h)


def test_wrong_chain_is_rejected(env):
    h = tx_hash(5)
    env.chain.broadcast(h, value=AMOUNT, chain_id=1)
    with pytest.raises(PaymentRejected, match="Неверная сеть"):
        env.payments.submit_transaction(env.invoice.id, h)


def test_malformed_hash_is_rejected(env):
    with pytest.raises(InvalidTransactionHash):
        env.payments.submit_transaction(env.invoice.id, "0x123")


def test_transaction_cannot_pay_two_invoices(env):
    h = tx_hash(6)
    env.chain.broadcast(h, value=AMOUNT)
    env.payments.submit_transaction(env.invoice.id, h)
    second = env.invoices.create_invoice(Decimal("0.001"), "Second")
    with pytest.raises(TransactionAlreadyUsed):
        env.payments.submit_transaction(second.id, h)


def test_resubmitting_same_hash_is_idempotent(env):
    h = tx_hash(7)
    env.chain.broadcast(h, value=AMOUNT)
    env.payments.submit_transaction(env.invoice.id, h)
    again = env.payments.submit_transaction(env.invoice.id, h)
    assert again.status is InvoiceStatus.CONFIRMING


def test_reverted_transaction_fails_invoice(env):
    h = tx_hash(8)
    env.chain.broadcast(h, value=AMOUNT)
    env.payments.submit_transaction(env.invoice.id, h)
    env.chain.mine(h, success=False)
    env.payments.process_pending()
    failed = env.repo.get(env.invoice.id)
    assert failed.status is InvoiceStatus.FAILED
    assert "reverted" in failed.failure_reason
    assert env.notifier.final_types == ["invoice.failed"]


def test_unknown_tx_is_accepted_then_validated_later(env):
    h = tx_hash(9)
    invoice = env.payments.submit_transaction(env.invoice.id, h)  # node does not know it yet
    assert invoice.status is InvoiceStatus.CONFIRMING
    assert invoice.payer_address is None

    env.chain.broadcast(h, value=AMOUNT - 1)  # appears, but underpaid
    env.payments.process_pending()
    failed = env.repo.get(env.invoice.id)
    assert failed.status is InvoiceStatus.FAILED
    assert "Недостаточная сумма" in failed.failure_reason


def test_unknown_tx_times_out(env):
    env.payments.submit_transaction(env.invoice.id, tx_hash(10))
    env.clock.advance(minutes=11)
    env.payments.process_pending()
    assert env.repo.get(env.invoice.id).status is InvoiceStatus.FAILED


def test_invoice_expires(env):
    env.clock.advance(minutes=16)
    assert env.invoices.expire_overdue() == 1
    assert env.repo.get(env.invoice.id).status is InvoiceStatus.EXPIRED
    assert env.notifier.final_types == ["invoice.expired"]


def test_cannot_pay_expired_invoice(env):
    h = tx_hash(11)
    env.chain.broadcast(h, value=AMOUNT)
    env.clock.advance(minutes=16)
    with pytest.raises(InvoiceNotPayable):
        env.payments.submit_transaction(env.invoice.id, h)


def test_custom_rule_can_be_added_without_changing_validator(env):
    """Open/Closed: a new rule plugs in from outside."""

    class MinimumPayerRule(ValidationRule):
        def check(self, invoice, tx):
            return "Плательщик заблокирован" if tx.from_address.endswith("2222") else None

    validator = PaymentValidator([*PaymentValidator().rules, MinimumPayerRule()])
    h = tx_hash(12)
    env.chain.broadcast(h, value=AMOUNT)
    assert validator.validate(env.invoice, env.chain.get_transaction(h)) == ["Плательщик заблокирован"]
