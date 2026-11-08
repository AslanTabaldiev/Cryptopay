"""События счёта и те, кто на них реагирует (паттерн «Наблюдатель»).

Сервисы сообщают о каждом шаге: счёт создан, транзакция получена, подтверждение,
оплачен… А PaymentNotifier-ы решают, что с этим делать:
  LoggingNotifier   — пишет всё в лог;
  TimelineNotifier  — сохраняет всё в хронологию счёта (её видно на странице оплаты);
  WebhookNotifier   — финальные события отправляет магазину POST-запросом с подписью HMAC;
  TelegramNotifier  — финальные события присылает продавцу в Telegram;
  CompositeNotifier — рассылает событие всем перечисленным.
Новый канал уведомлений = новый класс. Остальной код не меняется (принцип O из SOLID).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.database import TimelineRepository
from app.models import Invoice, TimelineEntry

log = logging.getLogger("cryptopay.notifications")

# События, о которых нужно сообщить магазину (счёт получил окончательный статус).
FINAL_EVENTS = {"invoice.paid", "invoice.failed", "invoice.expired"}


@dataclass(frozen=True)
class PaymentEvent:
    type: str          # "invoice.created", "transaction.received", …, "invoice.paid"
    invoice: Invoice
    occurred_at: datetime
    message: str = ""  # текст для хронологии и Telegram

    @property
    def is_final(self) -> bool:
        return self.type in FINAL_EVENTS

    def to_dict(self) -> dict:
        return {"type": self.type, "occurred_at": self.occurred_at.isoformat(), "invoice": self.invoice.to_dict()}


class PaymentNotifier(ABC):
    @abstractmethod
    def notify(self, event: PaymentEvent) -> None:
        """Обработать событие. Не должен выбрасывать исключение, если доставка не удалась."""


def _record(timeline: TimelineRepository | None, invoice: Invoice, kind: str, message: str) -> None:
    if timeline is not None:
        timeline.add(TimelineEntry(invoice.id, kind, message, datetime.now(timezone.utc)))


class LoggingNotifier(PaymentNotifier):
    def notify(self, event: PaymentEvent) -> None:
        log.info("%s счёт=%s %s", event.type, event.invoice.id, event.message)


class TimelineNotifier(PaymentNotifier):
    def __init__(self, timeline: TimelineRepository):
        self.timeline = timeline

    def notify(self, event: PaymentEvent) -> None:
        self.timeline.add(TimelineEntry(event.invoice.id, event.type, event.message, event.occurred_at))


class WebhookNotifier(PaymentNotifier):
    def __init__(self, url: str, secret: str, timeline: TimelineRepository | None = None):
        self.url = url
        self.secret = secret
        self.timeline = timeline  # чтобы показать в хронологии, дошёл ли вебхук

    def sign(self, body: bytes) -> str:
        return sign_webhook(body, self.secret)

    def notify(self, event: PaymentEvent) -> None:
        if not event.is_final:
            return
        body = json.dumps(event.to_dict()).encode()
        headers = {"Content-Type": "application/json", "X-Signature": self.sign(body), "X-Event-Type": event.type}
        try:
            response = httpx.post(self.url, content=body, headers=headers, timeout=10)
            response.raise_for_status()
            _record(self.timeline, event.invoice, "webhook.delivered",
                    f"Вебхук {event.type} доставлен магазину (ответ {response.status_code})")
        except httpx.HTTPError as exc:
            log.warning("Вебхук %s не доставлен: %s", event.type, exc)
            _record(self.timeline, event.invoice, "webhook.failed", f"Вебхук {event.type} не доставлен")


def sign_webhook(body: bytes, secret: str) -> str:
    """Подпись HMAC-SHA256. Магазин считает её сам и сравнивает — так он знает, что запрос от нас."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TelegramNotifier(PaymentNotifier):
    """Сообщение продавцу в Telegram через Bot API (бот создаётся у @BotFather)."""

    TITLES = {"invoice.paid": "💰 Счёт оплачен", "invoice.failed": "⚠️ Оплата не прошла",
              "invoice.expired": "⌛ Счёт истёк"}

    def __init__(self, bot_token: str, chat_id: str, explorer_url: str,
                 timeline: TimelineRepository | None = None, http: httpx.Client | None = None):
        self.url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self.chat_id = chat_id
        self.explorer_url = explorer_url
        self.timeline = timeline
        self.http = http or httpx.Client(timeout=10)

    def text(self, event: PaymentEvent) -> str:
        invoice = event.invoice
        data = invoice.to_dict()
        lines = [self.TITLES[event.type], f"{invoice.description} — {data['amount_eth']} ETH"]
        if invoice.order_id:
            lines.append(f"Заказ: {invoice.order_id}")
        if invoice.failure_reason:
            lines.append(f"Причина: {invoice.failure_reason}")
        if invoice.tx_hash:
            lines.append(f"{self.explorer_url}/tx/{invoice.tx_hash}")
        return "\n".join(lines)

    def notify(self, event: PaymentEvent) -> None:
        if not event.is_final:
            return
        try:
            self.http.post(self.url, json={"chat_id": self.chat_id, "text": self.text(event)}).raise_for_status()
            _record(self.timeline, event.invoice, "telegram.sent", "Продавец получил уведомление в Telegram")
        except httpx.HTTPError as exc:
            log.warning("Telegram: сообщение не отправлено: %s", type(exc).__name__)


class CompositeNotifier(PaymentNotifier):
    def __init__(self, notifiers: list[PaymentNotifier]):
        self.notifiers = notifiers

    def notify(self, event: PaymentEvent) -> None:
        for notifier in self.notifiers:
            try:
                notifier.notify(event)
            except Exception:  # один сломанный канал не должен мешать остальным
                log.exception("ошибка в %s", type(notifier).__name__)
