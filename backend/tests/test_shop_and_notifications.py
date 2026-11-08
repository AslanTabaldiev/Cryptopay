"""Демо-магазин (заказ → счёт → вебхук) и уведомления Telegram/вебхук."""

import json
from datetime import datetime, timezone

import httpx

from app.models import Invoice, InvoiceStatus
from app.notifications import PaymentEvent, TelegramNotifier, WebhookNotifier, sign_webhook
from tests.fakes import InMemoryTimelineRepository, make_client

SECRET = "test-secret"


def shop_client():
    client, chain, notifier, services = make_client(webhook_secret=SECRET)
    return client, services


def signed_webhook(client, event_type: str, invoice_id: str, secret: str = SECRET):
    body = json.dumps({"type": event_type, "occurred_at": "2026-01-01T00:00:00+00:00",
                       "invoice": {"id": invoice_id}}).encode()
    return client.post("/api/shop/webhook", content=body,
                       headers={"X-Signature": sign_webhook(body, secret), "Content-Type": "application/json"})


# ---------------------------------------------------------------- магазин
def test_products_are_listed():
    client, _ = shop_client()
    products = client.get("/api/shop/products").json()
    assert {p["id"] for p in products} == {"espresso", "latte", "croissant", "beans"}


def test_order_creates_invoice_with_correct_total():
    client, services = shop_client()
    r = client.post("/api/shop/orders", json={"items": {"latte": 2, "croissant": 1}})
    assert r.status_code == 201
    order = r.json()
    assert order["total_eth"] == "0.0014"  # 2 × 0.0005 + 0.0004
    assert order["status"] == "awaiting_payment"

    invoice = client.get(f"/api/invoices/{order['invoice_id']}").json()
    assert invoice["amount_eth"] == "0.0014"
    assert invoice["order_id"].startswith("SHOP-")
    assert "Латте ×2" in invoice["description"]


def test_bad_orders_are_rejected():
    client, _ = shop_client()
    assert client.post("/api/shop/orders", json={"items": {}}).json()["detail"] == "Корзина пуста"
    assert client.post("/api/shop/orders", json={"items": {"pizza": 1}}).status_code == 422


def test_order_becomes_paid_only_through_signed_webhook():
    client, _ = shop_client()
    order = client.post("/api/shop/orders", json={"items": {"espresso": 1}}).json()

    forged = signed_webhook(client, "invoice.paid", order["invoice_id"], secret="wrong-secret")
    assert forged.status_code == 401
    assert client.get(f"/api/shop/orders/{order['id']}").json()["status"] == "awaiting_payment"

    assert signed_webhook(client, "invoice.paid", order["invoice_id"]).status_code == 200
    paid = client.get(f"/api/shop/orders/{order['id']}").json()
    assert paid["status"] == "paid"
    assert paid["webhook_event"] == "invoice.paid"
    assert paid["webhook_at"] is not None


def test_webhook_for_unknown_invoice_is_ignored():
    client, _ = shop_client()
    r = signed_webhook(client, "invoice.paid", "not-a-shop-invoice")
    assert r.json() == {"ok": True, "order_id": None}


# ---------------------------------------------------------------- уведомления
def make_event(event_type: str) -> PaymentEvent:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    invoice = Invoice("inv1", 10**15, "0xabc", 11155111, "Латте ×2", "SHOP-1", InvoiceStatus.PAID, now, now, tx_hash="0x" + "a" * 64)
    return PaymentEvent(event_type, invoice, now, "текст")


def test_telegram_sends_only_final_events():
    sent = []
    http = httpx.Client(transport=httpx.MockTransport(lambda req: sent.append(json.loads(req.content)) or httpx.Response(200)))
    timeline = InMemoryTimelineRepository()
    telegram = TelegramNotifier("TOKEN", "42", "https://sepolia.etherscan.io", timeline, http=http)

    telegram.notify(make_event("transaction.received"))
    assert sent == []

    telegram.notify(make_event("invoice.paid"))
    assert sent[0]["chat_id"] == "42"
    assert sent[0]["text"].startswith("💰 Счёт оплачен")
    assert "Латте ×2 — 0.001 ETH" in sent[0]["text"]
    assert "sepolia.etherscan.io/tx/0x" in sent[0]["text"]
    assert timeline.entries[0].type == "telegram.sent"


def test_telegram_failure_does_not_raise():
    http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(401)))
    TelegramNotifier("BAD", "42", "https://x", http=http).notify(make_event("invoice.paid"))  # не падает


def test_webhook_ignores_intermediate_events(monkeypatch):
    calls = []
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: calls.append(kw) or httpx.Response(200, request=httpx.Request("POST", "http://x")))
    hook = WebhookNotifier("http://shop/webhook", SECRET)
    hook.notify(make_event("transaction.confirmation"))
    assert calls == []
    hook.notify(make_event("invoice.paid"))
    assert calls[0]["headers"]["X-Signature"] == sign_webhook(calls[0]["content"], SECRET)
