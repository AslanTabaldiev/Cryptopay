"""Переключатель API-ключа и русские сообщения об ошибках."""

import pytest

from tests.fakes import make_client

BODY = {"amount_eth": "0.001", "description": "Кофе"}


def test_key_is_off_by_default_and_shown_on_site():
    client, *_ = make_client()
    assert client.get("/api/config").json()["auth_required"] is False
    access = client.get("/api/access").json()
    assert access == {"required": False, "api_key": "cryptopay-demo-key"}
    assert client.post("/api/invoices", json=BODY).status_code == 201


def test_toggle_turns_key_check_on_and_off():
    client, *_ = make_client(api_key="secret")

    assert client.post("/api/access", json={"required": True}).json() == {"required": True, "api_key": "secret"}
    assert client.get("/api/config").json()["auth_required"] is True
    assert client.post("/api/invoices", json=BODY).status_code == 401
    assert client.post("/api/invoices", json=BODY, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.post("/api/invoices", json=BODY, headers={"X-API-Key": "secret"}).status_code == 201

    client.post("/api/access", json={"required": False})
    assert client.post("/api/invoices", json=BODY).status_code == 201


def test_key_required_from_settings():
    client, *_ = make_client(api_key="k", api_key_required=True)
    assert client.post("/api/invoices", json=BODY).status_code == 401


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
    client, *_ = make_client()
    r = client.post("/api/invoices", json=body)
    assert r.status_code == 422
    assert r.json()["detail"] == expected
