"""Режимы доступа к API магазина и русские сообщения об ошибках."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.container import Container
from app.main import create_app
from tests.fakes import MERCHANT, FakeBlockchain, InMemoryInvoiceRepository, RecordingNotifier


def make_client(api_key: str) -> TestClient:
    settings = Settings(
        database_url="sqlite://", rpc_url="http://unused", chain_id=11155111, network_name="Sepolia",
        explorer_url="https://sepolia.etherscan.io", merchant_address=MERCHANT, merchant_api_key=api_key,
        required_confirmations=1, default_ttl_minutes=15, tx_not_found_timeout_minutes=10,
        poll_interval_seconds=60, webhook_url=None, webhook_secret="s", run_watcher=False,
    )
    container = Container.build(
        settings, repo=InMemoryInvoiceRepository(), chain=FakeBlockchain(), notifier=RecordingNotifier()
    )
    return TestClient(create_app(container))


BODY = {"amount_eth": "0.001", "description": "Кофе"}


def test_demo_mode_needs_no_key():
    client = make_client(api_key="")
    assert client.get("/api/config").json()["auth_required"] is False
    assert client.post("/api/invoices", json=BODY).status_code == 201
    assert client.get("/api/invoices").status_code == 200


def test_protected_mode_requires_key():
    client = make_client(api_key="secret")
    assert client.get("/api/config").json()["auth_required"] is True
    assert client.post("/api/invoices", json=BODY).status_code == 401
    assert client.post("/api/invoices", json=BODY, headers={"X-API-Key": "secret"}).status_code == 201


@pytest.mark.parametrize(
    "body, expected",
    [
        ({"amount_eth": "-1", "description": "x"}, "Сумма: должно быть больше 0"),
        ({"amount_eth": "abc", "description": "x"}, "Сумма: должно быть числом"),
        ({"amount_eth": "0.001", "description": ""}, "Описание: не может быть пустым"),
        ({"description": "x"}, "Сумма: обязательное поле"),
    ],
)
def test_validation_errors_are_in_russian(body, expected):
    r = make_client(api_key="").post("/api/invoices", json=body)
    assert r.status_code == 422
    assert r.json()["detail"] == expected
