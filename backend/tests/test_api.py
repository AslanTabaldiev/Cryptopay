"""Сквозные тесты API: настоящий FastAPI + настоящая база SQLite, фейковый блокчейн."""

from decimal import Decimal

import pytest

from app.database import make_engine
from app.models import eth_to_wei
from tests.fakes import MERCHANT, make_client, tx_hash

API_KEY = "test-key"
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture
def ctx(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    client, chain, notifier, services = make_client(engine=engine, api_key=API_KEY, api_key_required=True)
    with client:
        yield client, chain, notifier, services


def create(client, **overrides):
    return client.post("/api/invoices", json={"amount_eth": "0.001", "description": "Кофе", **overrides}, headers=HEADERS)


def test_health(ctx):
    client, *_ = ctx
    assert client.get("/health").json() == {"status": "ok"}


def test_create_requires_api_key_when_enabled(ctx):
    client, *_ = ctx
    assert client.post("/api/invoices", json={"amount_eth": "0.001", "description": "x"}).status_code == 401
    assert client.get("/api/invoices", headers={"X-API-Key": "wrong"}).status_code == 401


def test_create_validates_body(ctx):
    client, *_ = ctx
    assert create(client, amount_eth="-1").status_code == 422
    assert create(client, description="").status_code == 422


def test_create_and_get_invoice(ctx):
    client, *_ = ctx
    r = create(client, order_id="ORDER-1")
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "awaiting_payment"
    assert data["amount_wei"] == str(10**15)
    assert data["amount_eth"] == "0.001"
    assert data["recipient"] == MERCHANT
    assert data["payment_path"] == f"/pay/{data['id']}"

    public = client.get(f"/api/invoices/{data['id']}")  # страница оплаты — без ключа
    assert public.status_code == 200
    assert public.json()["order_id"] == "ORDER-1"

    listing = client.get("/api/invoices", headers=HEADERS).json()
    assert [i["id"] for i in listing] == [data["id"]]


def test_unknown_invoice_is_404(ctx):
    client, *_ = ctx
    assert client.get("/api/invoices/nope").status_code == 404


def test_pay_invoice_end_to_end(ctx):
    client, chain, notifier, services = ctx
    invoice_id = create(client).json()["id"]
    h = tx_hash(42)
    chain.broadcast(h, value=eth_to_wei(Decimal("0.001")))

    r = client.post(f"/api/invoices/{invoice_id}/transaction", json={"tx_hash": h})
    assert r.status_code == 200
    assert r.json()["status"] == "confirming"
    assert r.json()["explorer_tx_url"].endswith(h)

    chain.mine(h)
    services.watcher.tick()
    final = client.get(f"/api/invoices/{invoice_id}").json()
    assert final["status"] == "paid"
    assert final["confirmations"] == 1
    assert notifier.final_types == ["invoice.paid"]


def test_rejected_payment_returns_422_with_reason(ctx):
    client, chain, *_ = ctx
    invoice_id = create(client).json()["id"]
    h = tx_hash(43)
    chain.broadcast(h, value=1)
    r = client.post(f"/api/invoices/{invoice_id}/transaction", json={"tx_hash": h})
    assert r.status_code == 422
    assert "Недостаточная сумма" in r.json()["detail"]


def test_tx_reuse_returns_409(ctx):
    client, chain, *_ = ctx
    first = create(client).json()["id"]
    second = create(client).json()["id"]
    h = tx_hash(44)
    chain.broadcast(h, value=eth_to_wei(Decimal("0.001")))
    assert client.post(f"/api/invoices/{first}/transaction", json={"tx_hash": h}).status_code == 200
    assert client.post(f"/api/invoices/{second}/transaction", json={"tx_hash": h}).status_code == 409


def test_timeline_shows_every_step(ctx):
    client, chain, _, services = ctx
    invoice_id = create(client).json()["id"]
    h = tx_hash(45)
    chain.broadcast(h, value=eth_to_wei(Decimal("0.001")))
    client.post(f"/api/invoices/{invoice_id}/transaction", json={"tx_hash": h})
    chain.mine(h)
    services.watcher.tick()

    events = client.get(f"/api/invoices/{invoice_id}/events").json()
    assert [e["type"] for e in events] == [
        "invoice.created", "transaction.received", "transaction.confirmation", "invoice.paid",
    ]
    assert "Проверка пройдена" in events[1]["message"]
    assert "подтверждение 1 из 1" in events[2]["message"]
    assert client.get("/api/invoices/nope/events").status_code == 404
