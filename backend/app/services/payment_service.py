"""Use cases around paying an invoice: accept a tx hash, track confirmations."""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from app.domain.errors import (
    InvalidTransactionHash,
    InvoiceNotFound,
    InvoiceNotPayable,
    PaymentRejected,
    TransactionAlreadyUsed,
)
from app.domain.invoice import Invoice, InvoiceStatus
from app.ports.blockchain import BlockchainError, BlockchainGateway, ChainTransaction
from app.ports.notifier import PaymentEvent, PaymentNotifier
from app.ports.repository import InvoiceRepository
from app.services.clock import Clock, utc_now
from app.services.validation import PaymentValidator

log = logging.getLogger("cryptopay.payments")

TX_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


class PaymentService:
    def __init__(
        self,
        repo: InvoiceRepository,
        chain: BlockchainGateway,
        validator: PaymentValidator,
        notifier: PaymentNotifier,
        *,
        required_confirmations: int,
        tx_not_found_timeout_minutes: int,
        clock: Clock = utc_now,
    ):
        self._repo = repo
        self._chain = chain
        self._validator = validator
        self._notifier = notifier
        self._required = max(1, required_confirmations)
        self._not_found_timeout = timedelta(minutes=tx_not_found_timeout_minutes)
        self._clock = clock

    @property
    def required_confirmations(self) -> int:
        return self._required

    # ------------------------------------------------------------------ submit
    def submit_transaction(self, invoice_id: str, tx_hash: str) -> Invoice:
        tx_hash = tx_hash.strip().lower()
        if not TX_HASH_RE.match(tx_hash):
            raise InvalidTransactionHash(tx_hash)

        invoice = self._repo.get(invoice_id)
        if invoice is None:
            raise InvoiceNotFound(invoice_id)

        now = self._clock()
        if invoice.tx_hash == tx_hash:
            return invoice  # idempotent: the page may retry the same request
        if invoice.is_overdue(now):
            invoice.expire(now)
            self._repo.update(invoice)
            self._notify("invoice.expired", invoice)
        if invoice.status is not InvoiceStatus.AWAITING_PAYMENT:
            raise InvoiceNotPayable(invoice.status.value)

        if self._repo.get_by_tx_hash(tx_hash) is not None:
            raise TransactionAlreadyUsed(tx_hash)

        tx = self._chain.get_transaction(tx_hash)
        if tx is not None:
            errors = self._validator.validate(invoice, tx)
            if errors:
                raise PaymentRejected(errors)
        # If the node does not know the tx yet (fresh broadcast), accept it for now;
        # the watcher validates it as soon as it appears (see refresh()).
        invoice.attach_transaction(tx_hash, tx.from_address if tx else None, now)
        self._repo.update(invoice)

        try:
            return self.refresh(invoice)
        except BlockchainError as exc:
            log.warning("Immediate refresh of %s failed: %s", invoice.id, exc)
            return invoice

    # ----------------------------------------------------------------- refresh
    def refresh(self, invoice: Invoice) -> Invoice:
        """Advance a CONFIRMING invoice using the current blockchain state."""
        if invoice.status is not InvoiceStatus.CONFIRMING or invoice.tx_hash is None:
            return invoice
        now = self._clock()

        # payer_address is None  <=>  the tx was not visible at submit time and is not validated yet.
        if invoice.payer_address is None:
            tx = self._chain.get_transaction(invoice.tx_hash)
            if tx is None:
                if now - (invoice.tx_submitted_at or now) > self._not_found_timeout:
                    return self._fail(invoice, "Транзакция не найдена в сети")
                return invoice
            if not self._accept_late_transaction(invoice, tx):
                return invoice

        receipt = self._chain.get_receipt(invoice.tx_hash)
        if receipt is None:
            return invoice  # still in the mempool
        if not receipt.success:
            return self._fail(invoice, "Транзакция отклонена сетью (reverted)")

        confirmations = self._chain.get_block_number() - receipt.block_number + 1
        invoice.update_confirmations(confirmations, now)
        if invoice.confirmations >= self._required:
            invoice.mark_paid(now)
            self._repo.update(invoice)
            self._notify("invoice.paid", invoice)
        else:
            self._repo.update(invoice)
        return invoice

    def process_pending(self) -> int:
        """Called by the PaymentWatcher. Returns how many invoices reached a final status."""
        finished = 0
        for invoice in self._repo.list_by_status(InvoiceStatus.CONFIRMING):
            try:
                if self.refresh(invoice).is_final():
                    finished += 1
            except BlockchainError as exc:
                log.warning("Could not refresh invoice %s: %s", invoice.id, exc)
        return finished

    # ----------------------------------------------------------------- helpers
    def _accept_late_transaction(self, invoice: Invoice, tx: ChainTransaction) -> bool:
        errors = self._validator.validate(invoice, tx)
        if errors:
            self._fail(invoice, "; ".join(errors))
            return False
        invoice.payer_address = tx.from_address
        self._repo.update(invoice)
        return True

    def _fail(self, invoice: Invoice, reason: str) -> Invoice:
        invoice.mark_failed(reason, self._clock())
        self._repo.update(invoice)
        self._notify("invoice.failed", invoice)
        return invoice

    def _notify(self, event_type: str, invoice: Invoice) -> None:
        self._notifier.notify(PaymentEvent(event_type, invoice, self._clock()))
