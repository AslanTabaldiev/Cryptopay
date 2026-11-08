"""Фоновый процесс: каждые несколько секунд просрочивает старые счета и проверяет подтверждения."""

from __future__ import annotations

import asyncio
import logging

from app.payments import InvoiceService, PaymentService

log = logging.getLogger("cryptopay.watcher")


class PaymentWatcher:
    def __init__(self, invoices: InvoiceService, payments: PaymentService, interval_seconds: float):
        self.invoices = invoices
        self.payments = payments
        self.interval = interval_seconds
        self.task: asyncio.Task | None = None

    def tick(self) -> None:
        """Один проход проверки. Ошибка в одном проходе не останавливает следующие."""
        try:
            expired = self.invoices.expire_overdue()
            finished = self.payments.process_pending()
            if expired or finished:
                log.info("просрочено: %d, завершено: %d", expired, finished)
        except Exception:
            log.exception("ошибка фоновой проверки")

    async def run(self) -> None:
        while True:
            await asyncio.to_thread(self.tick)  # сервисы синхронные (база + HTTP)
            await asyncio.sleep(self.interval)

    def start(self) -> None:
        self.task = self.task or asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
