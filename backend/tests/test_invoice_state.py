from datetime import timedelta

import pytest

from app.domain.invoice import InvalidStateTransition, Invoice, InvoiceStatus
from tests.fakes import MERCHANT, SEPOLIA, FakeClock, tx_hash


def make_invoice(clock: FakeClock) -> Invoice:
    return Invoice.create(
        amount_wei=10**15,
        recipient=MERCHANT,
        chain_id=SEPOLIA,
        description="test",
        order_id=None,
        ttl=timedelta(minutes=15),
        now=clock(),
    )


def test_new_invoice_awaits_payment():
    invoice = make_invoice(FakeClock())
    assert invoice.status is InvoiceStatus.AWAITING_PAYMENT
    assert not invoice.is_final()


def test_amount_must_be_positive():
    with pytest.raises(ValueError):
        Invoice.create(
            amount_wei=0, recipient=MERCHANT, chain_id=SEPOLIA, description="x",
            order_id=None, ttl=timedelta(minutes=1), now=FakeClock()(),
        )


def test_happy_path_transitions():
    clock = FakeClock()
    invoice = make_invoice(clock)
    invoice.attach_transaction(tx_hash(1), "0xABC", clock())
    assert invoice.status is InvoiceStatus.CONFIRMING
    assert invoice.payer_address == "0xabc"
    invoice.update_confirmations(2, clock())
    invoice.mark_paid(clock())
    assert invoice.status is InvoiceStatus.PAID
    assert invoice.is_final()


def test_overdue_and_expire():
    clock = FakeClock()
    invoice = make_invoice(clock)
    clock.advance(minutes=16)
    assert invoice.is_overdue(clock())
    invoice.expire(clock())
    assert invoice.status is InvoiceStatus.EXPIRED


@pytest.mark.parametrize(
    "action",
    [
        lambda inv, now: inv.mark_paid(now),
        lambda inv, now: inv.mark_failed("x", now),
        lambda inv, now: inv.update_confirmations(1, now),
    ],
)
def test_illegal_transitions_from_awaiting(action):
    clock = FakeClock()
    invoice = make_invoice(clock)
    with pytest.raises(InvalidStateTransition):
        action(invoice, clock())


def test_final_states_are_terminal():
    clock = FakeClock()
    invoice = make_invoice(clock)
    invoice.expire(clock())
    with pytest.raises(InvalidStateTransition):
        invoice.attach_transaction(tx_hash(1), None, clock())
