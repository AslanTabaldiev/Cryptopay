"""HTTP request/response models (OpenAPI schema is generated from these)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.domain.invoice import Invoice, InvoiceStatus
from app.serialization import wei_to_eth


class CreateInvoiceRequest(BaseModel):
    amount_eth: Decimal = Field(gt=0, le=1000, examples=["0.001"], description="Amount in ETH")
    description: str = Field(min_length=1, max_length=255, examples=["Coffee beans 250g"])
    order_id: str | None = Field(default=None, max_length=128, examples=["ORDER-1042"])
    ttl_minutes: int | None = Field(default=None, ge=1, le=1440, description="Invoice lifetime")


class SubmitTransactionRequest(BaseModel):
    tx_hash: str = Field(examples=["0x" + "ab" * 32])


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

    @classmethod
    def from_entity(
        cls, invoice: Invoice, *, network_name: str, explorer_url: str, required_confirmations: int
    ) -> "InvoiceResponse":
        return cls(
            id=invoice.id,
            order_id=invoice.order_id,
            description=invoice.description,
            status=invoice.status,
            amount_wei=str(invoice.amount_wei),
            amount_eth=wei_to_eth(invoice.amount_wei),
            recipient=invoice.recipient,
            chain_id=invoice.chain_id,
            network_name=network_name,
            tx_hash=invoice.tx_hash,
            payer_address=invoice.payer_address,
            confirmations=invoice.confirmations,
            required_confirmations=required_confirmations,
            failure_reason=invoice.failure_reason,
            created_at=invoice.created_at,
            expires_at=invoice.expires_at,
            paid_at=invoice.paid_at,
            explorer_tx_url=f"{explorer_url}/tx/{invoice.tx_hash}" if invoice.tx_hash else None,
            payment_path=f"/pay/{invoice.id}",
        )


class ConfigResponse(BaseModel):
    chain_id: int
    network_name: str
    explorer_url: str
    merchant_address: str
    required_confirmations: int


class ErrorResponse(BaseModel):
    detail: str
