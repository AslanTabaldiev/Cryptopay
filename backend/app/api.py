"""REST API: схемы запросов/ответов, проверка API-ключа и маршруты.

Маршруты «тонкие»: прочитать запрос → вызвать сервис → вернуть ответ.
Вся логика живёт в payments.py.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.models import Invoice, InvoiceStatus

router = APIRouter(prefix="/api")


# ================================================================ схемы
class CreateInvoiceRequest(BaseModel):
    amount_eth: Decimal = Field(gt=0, le=1000, examples=["0.001"], description="Сумма в ETH")
    description: str = Field(min_length=1, max_length=255, examples=["Кофе в зёрнах 250 г"])
    order_id: str | None = Field(default=None, max_length=128, examples=["ORDER-1042"])
    ttl_minutes: int | None = Field(default=None, ge=1, le=1440, description="Срок действия счёта, минуты")


class SubmitTransactionRequest(BaseModel):
    tx_hash: str = Field(examples=["0x" + "ab" * 32])


class AccessRequest(BaseModel):
    required: bool = Field(description="Требовать ли X-API-Key для создания и просмотра счетов")


class InvoiceResponse(BaseModel):
    id: str
    order_id: str | None
    description: str
    status: InvoiceStatus
    amount_wei: str
    amount_eth: str
    recipient: str
    chain_id: int
    network_name: str
    tx_hash: str | None
    payer_address: str | None
    confirmations: int
    required_confirmations: int
    failure_reason: str | None
    created_at: datetime
    expires_at: datetime
    paid_at: datetime | None
    explorer_tx_url: str | None
    payment_path: str


class ConfigResponse(BaseModel):
    chain_id: int
    network_name: str
    explorer_url: str
    merchant_address: str
    required_confirmations: int
    auth_required: bool


class AccessResponse(BaseModel):
    required: bool
    api_key: str


# ================================================================ API-ключ
class ApiKeyGuard:
    """Проверка API-ключа магазина, которую можно включить или выключить.

    Учебный проект: ключ не секретный — он показан на сайте, а проверку
    включает переключатель в кабинете. В настоящем магазине переключателя
    не было бы, а ключ хранился бы только у продавца.
    """

    def __init__(self, api_key: str, required: bool):
        self.api_key = api_key
        self.required = required

    def check(self, provided: str | None) -> None:
        if not self.required:
            return
        if not provided or not secrets.compare_digest(provided, self.api_key):
            raise HTTPException(401, "Неверный или отсутствующий X-API-Key")


def services(request: Request):
    """Достаёт сервисы, собранные в main.py (внедрение зависимостей)."""
    return request.app.state.services


def require_api_key(x_api_key: str | None = Header(default=None), s=Depends(services)) -> None:
    s.guard.check(x_api_key)


def present(invoice: Invoice, s) -> InvoiceResponse:
    data = invoice.to_dict()
    return InvoiceResponse(
        **data,
        network_name=s.settings.network_name,
        required_confirmations=s.payments.required_confirmations,
        explorer_tx_url=f"{s.settings.explorer_url}/tx/{invoice.tx_hash}" if invoice.tx_hash else None,
        payment_path=f"/pay/{invoice.id}",
    )


# ================================================================ маршруты
@router.get("/config", response_model=ConfigResponse, tags=["Публичные"])
def get_config(s=Depends(services)):
    return ConfigResponse(
        chain_id=s.settings.chain_id,
        network_name=s.settings.network_name,
        explorer_url=s.settings.explorer_url,
        merchant_address=s.settings.merchant_address,
        required_confirmations=s.payments.required_confirmations,
        auth_required=s.guard.required,
    )


@router.get("/access", response_model=AccessResponse, tags=["Учебный режим"])
def get_access(s=Depends(services)):
    """Показать, включена ли проверка ключа, и сам ключ (только для учебного проекта)."""
    return AccessResponse(required=s.guard.required, api_key=s.guard.api_key)


@router.post("/access", response_model=AccessResponse, tags=["Учебный режим"])
def set_access(body: AccessRequest, s=Depends(services)):
    """Переключатель «Требовать API-ключ». Действует до перезапуска сервера."""
    s.guard.required = body.required
    return AccessResponse(required=s.guard.required, api_key=s.guard.api_key)


@router.post("/invoices", response_model=InvoiceResponse, status_code=201,
             dependencies=[Depends(require_api_key)], tags=["Магазин"])
def create_invoice(body: CreateInvoiceRequest, s=Depends(services)):
    invoice = s.invoices.create_invoice(body.amount_eth, body.description, body.order_id, body.ttl_minutes)
    return present(invoice, s)


@router.get("/invoices", response_model=list[InvoiceResponse],
            dependencies=[Depends(require_api_key)], tags=["Магазин"])
def list_invoices(limit: int = Query(50, ge=1, le=200), s=Depends(services)):
    return [present(i, s) for i in s.invoices.list_invoices(limit)]


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse, tags=["Публичные"])
def get_invoice(invoice_id: str, s=Depends(services)):
    return present(s.invoices.get_invoice(invoice_id), s)


@router.get("/invoices/{invoice_id}/events", tags=["Публичные"])
def get_invoice_events(invoice_id: str, s=Depends(services)):
    """Хронология счёта: что и когда произошло (видна на странице оплаты)."""
    s.invoices.get_invoice(invoice_id)  # 404, если счёта нет
    return [entry.to_dict() for entry in s.timeline.list_for(invoice_id)]


@router.post("/invoices/{invoice_id}/transaction", response_model=InvoiceResponse, tags=["Публичные"])
def submit_transaction(invoice_id: str, body: SubmitTransactionRequest, s=Depends(services)):
    return present(s.payments.submit_transaction(invoice_id, body.tx_hash), s)


# ================================================================ понятные ошибки
FIELD_NAMES = {
    "amount_eth": "Сумма",
    "description": "Описание",
    "order_id": "Номер заказа",
    "ttl_minutes": "Срок действия",
    "tx_hash": "Хэш транзакции",
    "required": "Переключатель",
    "limit": "Лимит",
}


def _error_text(error: dict) -> str:
    kind, ctx = error.get("type", ""), error.get("ctx") or {}
    messages = {
        "missing": "обязательное поле",
        "greater_than": f"должно быть больше {ctx.get('gt')}",
        "greater_than_equal": f"должно быть не меньше {ctx.get('ge')}",
        "less_than_equal": f"должно быть не больше {ctx.get('le')}",
        "string_too_short": "не может быть пустым",
        "string_too_long": f"слишком длинное (максимум {ctx.get('max_length')} символов)",
        "decimal_parsing": "должно быть числом",
        "int_parsing": "должно быть числом",
        "bool_parsing": "должно быть true или false",
    }
    return messages.get(kind, "некорректное значение")


def describe_validation_errors(errors: list[dict]) -> str:
    """Русский текст вместо стандартных английских ошибок Pydantic."""
    parts = []
    for error in errors:
        field = next((str(p) for p in reversed(error.get("loc", ())) if p not in ("body", "query", "path")), "")
        name = FIELD_NAMES.get(field, field)
        parts.append(f"{name}: {_error_text(error)}" if name else _error_text(error))
    return "; ".join(parts) or "Некорректный запрос"
