"""Shared JSON representation of an invoice (used by webhooks)."""

from __future__ import annotations

from decimal import Decimal

from app.domain.invoice import Invoice

WEI_PER_ETH = Decimal(10) ** 18


def wei_to_eth(wei: int) -> str:
    return format((Decimal(wei) / WEI_PER_ETH).normalize(), "f")


def invoice_to_dict(invoice: Invoice) -> dict:
    def iso(value):
        return value.isoformat() if value else None

    return {
        "id": invoice.id,
        "order_id": invoice.order_id,
        "description": invoice.description,
        "status": invoice.status.value,
        "amount_wei": str(invoice.amount_wei),
        "amount_eth": wei_to_eth(invoice.amount_wei),
        "recipient": invoice.recipient,
        "chain_id": invoice.chain_id,
        "tx_hash": invoice.tx_hash,
        "payer_address": invoice.payer_address,
        "confirmations": invoice.confirmations,
        "failure_reason": invoice.failure_reason,
        "created_at": iso(invoice.created_at),
        "expires_at": iso(invoice.expires_at),
        "paid_at": iso(invoice.paid_at),
    }
