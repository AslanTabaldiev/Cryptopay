"""Adapters: PaymentNotifier implementations (log, signed webhook, composite)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

import httpx

from app.ports.notifier import PaymentEvent, PaymentNotifier
from app.serialization import invoice_to_dict

log = logging.getLogger("cryptopay.notifier")


def event_payload(event: PaymentEvent) -> dict:
    return {
        "type": event.type,
        "occurred_at": event.occurred_at.isoformat(),
        "invoice": invoice_to_dict(event.invoice),
    }


class LoggingNotifier(PaymentNotifier):
    def notify(self, event: PaymentEvent) -> None:
        log.info("%s invoice=%s tx=%s", event.type, event.invoice.id, event.invoice.tx_hash)


class WebhookNotifier(PaymentNotifier):
    """POSTs the event as JSON; the body is signed with HMAC-SHA256 in `X-Signature`."""

    def __init__(self, url: str, secret: str, client: httpx.Client | None = None):
        self._url = url
        self._secret = secret.encode()
        self._http = client or httpx.Client(timeout=5.0)

    def sign(self, body: bytes) -> str:
        return hmac.new(self._secret, body, hashlib.sha256).hexdigest()

    def notify(self, event: PaymentEvent) -> None:
        body = json.dumps(event_payload(event), separators=(",", ":")).encode()
        headers = {
            "Content-Type": "application/json",
            "X-Signature": self.sign(body),
            "X-Event-Type": event.type,
        }
        try:
            self._http.post(self._url, content=body, headers=headers).raise_for_status()
        except httpx.HTTPError as exc:  # delivery failure must not break payment processing
            log.warning("Webhook %s for invoice %s failed: %s", event.type, event.invoice.id, exc)


class CompositeNotifier(PaymentNotifier):
    def __init__(self, notifiers: list[PaymentNotifier]):
        self._notifiers = notifiers

    def notify(self, event: PaymentEvent) -> None:
        for notifier in self._notifiers:
            notifier.notify(event)
