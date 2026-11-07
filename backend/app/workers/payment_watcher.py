"""Background loop that expires overdue invoices and tracks confirmations."""

from __future__ import annotations

import asyncio
import logging

from app.services.invoice_service import InvoiceService
from app.services.payment_service import PaymentService

log = logging.getLogger("cryptopay.watcher")


class PaymentWatcher:
    def __init__(self, invoices: InvoiceService, payments: PaymentService, interval_seconds: float):
        self._invoices = invoices
        self._payments = payments
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None

    def tick(self) -> None:
        try:
            expired = self._invoices.expire_overdue()
            finished = self._payments.process_pending()
            if expired or finished:
                log.info("watcher: %d expired, %d finished", expired, finished)
        except Exception:  # never let one bad iteration kill the loop
            log.exception("watcher iteration failed")

    async def _run(self) -> None:
        while True:
            await asyncio.to_thread(self.tick)  # services are synchronous (DB + HTTP)
            await asyncio.sleep(self._interval)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="payment-watcher")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
