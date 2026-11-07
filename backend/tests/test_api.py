"""End-to-end API tests: real FastAPI app + real SQLAlchemy repository (SQLite), fake blockchain."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.adapters.sql_repository import SqlAlchemyInvoiceRepository, create_db_engine
from app.config import Settings
from app.container import Container
from app.main import create_app
from app.services.invoice_service import eth_to_wei
from tests.fakes import MERCHANT, FakeBlockchain, RecordingNotifier, tx_hash

API_KEY = "test-key"


@pytest.fixture
def ctx(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        rpc_url="http://unused",
        chain_id=11155111,
        network_name="Sepolia",
        explorer_url="https://sepolia.etherscan.io",
        merchant_address=MERCHANT,
        merchant_api_key=API_KEY,
        required_confirmations=1,
        default_ttl_minutes=15,
        tx_not_found_timeout_minutes=10,
        poll_interval_seconds=60,
        webhook_url=None,
        webhook_secret="s",
        cors_origins=["http://localhost:5173"],
        run_watcher=False,
    )
    chain = FakeBlockchain()
    notifier = RecordingNotifier()
    repo = SqlAlchemyInvoiceRepository(create_db_engine(settings.database_url))
    container = Container.build(settings, repo=repo, chain=chain, notifier=notifier)
    with TestClient(create_app(container)) as client:
        yield client, chain, notifier, container


def create(client, **overrides):
    body = {"amount_eth": "0.001", "description": "Coffee", **overrides}
    return client.post("/api/invoices", json=body, headers={"X-API-Key": API_KEY})


def test_health(ctx):
    client, *_ = ctx
    assert client.get("/health").json() == {"status": "ok"}


def test_create_requires_api_key(ctx):
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

    public = client.get(f"/api/invoices/{data['id']}")
    assert public.status_code == 200
    assert public.json()["order_id"] == "ORDER-1"

    listing = client.get("/api/invoices", headers={"X-API-Key": API_KEY}).json()
    assert [i["id"] for i in listing] == [data["id"]]


def test_unknown_invoice_is_404(ctx):
    client, *_ = ctx
    assert client.get("/api/invoices/nope").status_code == 404


def test_pay_invoice_end_to_end(ctx):
    client, chain, notifier, container = ctx
    invoice_id = create(client).json()["id"]
    h = tx_hash(42)
    chain.broadcast(h, value=eth_to_wei(Decimal("0.001")))

    r = client.post(f"/api/invoices/{invoice_id}/transaction", json={"tx_hash": h})
    assert r.status_code == 200
    assert r.json()["status"] == "confirming"
    assert r.json()["explorer_tx_url"].endswith(h)

    chain.mine(h)
    container.watcher.tick()
    final = client.get(f"/api/invoices/{invoice_id}").json()
    assert final["status"] == "paid"
    assert final["confirmations"] == 1
    assert notifier.types == ["invoice.paid"]


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
