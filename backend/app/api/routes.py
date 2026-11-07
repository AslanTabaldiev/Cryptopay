"""HTTP endpoints. Thin layer: parse input, call a service, shape the output."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_container, require_api_key
from app.api.schemas import (
    ConfigResponse,
    CreateInvoiceRequest,
    ErrorResponse,
    InvoiceResponse,
    SubmitTransactionRequest,
)
from app.container import Container
from app.domain.invoice import Invoice

router = APIRouter(prefix="/api")


def _present(invoice: Invoice, c: Container) -> InvoiceResponse:
    return InvoiceResponse.from_entity(
        invoice,
        network_name=c.settings.network_name,
        explorer_url=c.settings.explorer_url,
        required_confirmations=c.payment_service.required_confirmations,
    )


@router.get("/config", response_model=ConfigResponse, tags=["public"])
def get_config(c: Container = Depends(get_container)) -> ConfigResponse:
    s = c.settings
    return ConfigResponse(
        chain_id=s.chain_id,
        network_name=s.network_name,
        explorer_url=s.explorer_url,
        merchant_address=s.merchant_address,
        required_confirmations=c.payment_service.required_confirmations,
    )


@router.post(
    "/invoices",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
    responses={401: {"model": ErrorResponse}},
    tags=["merchant"],
)
def create_invoice(body: CreateInvoiceRequest, c: Container = Depends(get_container)) -> InvoiceResponse:
    invoice = c.invoice_service.create_invoice(
        amount_eth=body.amount_eth,
        description=body.description,
        order_id=body.order_id,
        ttl_minutes=body.ttl_minutes,
    )
    return _present(invoice, c)


@router.get(
    "/invoices",
    response_model=list[InvoiceResponse],
    dependencies=[Depends(require_api_key)],
    responses={401: {"model": ErrorResponse}},
    tags=["merchant"],
)
def list_invoices(
    limit: int = Query(50, ge=1, le=200), c: Container = Depends(get_container)
) -> list[InvoiceResponse]:
    return [_present(i, c) for i in c.invoice_service.list_invoices(limit)]


@router.get(
    "/invoices/{invoice_id}",
    response_model=InvoiceResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["public"],
)
def get_invoice(invoice_id: str, c: Container = Depends(get_container)) -> InvoiceResponse:
    return _present(c.invoice_service.get_invoice(invoice_id), c)


@router.post(
    "/invoices/{invoice_id}/transaction",
    response_model=InvoiceResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    tags=["public"],
)
def submit_transaction(
    invoice_id: str, body: SubmitTransactionRequest, c: Container = Depends(get_container)
) -> InvoiceResponse:
    return _present(c.payment_service.submit_transaction(invoice_id, body.tx_hash), c)
