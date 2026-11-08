"""Демо-магазин «Кофейня» — пример клиента платёжного шлюза.

Магазин делает то же, что делал бы настоящий интернет-магазин:
  1. покупатель собирает корзину → магазин создаёт заказ и счёт в шлюзе;
  2. покупатель платит счёт на странице оплаты шлюза;
  3. шлюз присылает магазину вебхук invoice.paid, магазин проверяет подпись
     HMAC и только после этого помечает заказ оплаченным.

Статус заказа меняется ТОЛЬКО через вебхук — так видно, что интеграция работает.
"""

from __future__ import annotations

import hmac
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from app.database import Base
from app.models import eth_to_wei, wei_to_eth
from app.notifications import sign_webhook
from app.payments import Clock, InvoiceService, utc_now

# ---------------------------------------------------------------- витрина
PRODUCTS = {
    "espresso": {"name": "Эспрессо", "emoji": "☕", "note": "Двойной, 60 мл", "price_eth": "0.0003"},
    "latte": {"name": "Латте", "emoji": "🥛", "note": "На овсяном молоке", "price_eth": "0.0005"},
    "croissant": {"name": "Круассан", "emoji": "🥐", "note": "Свежий, с маслом", "price_eth": "0.0004"},
    "beans": {"name": "Кофе в зёрнах", "emoji": "🫘", "note": "Эфиопия, 250 г", "price_eth": "0.001"},
}

# Статус заказа ← событие из вебхука
STATUS_BY_EVENT = {"invoice.paid": "paid", "invoice.failed": "failed", "invoice.expired": "expired"}


@dataclass
class ShopOrder:
    id: str
    items: list[dict]          # [{"product_id", "name", "qty", "price_eth"}]
    total_wei: int
    invoice_id: str
    status: str                # awaiting_payment | paid | failed | expired
    created_at: datetime
    webhook_event: str | None = None
    webhook_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "items": self.items,
            "total_eth": wei_to_eth(self.total_wei),
            "invoice_id": self.invoice_id,
            "payment_path": f"/pay/{self.invoice_id}",
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "webhook_event": self.webhook_event,
            "webhook_at": self.webhook_at.isoformat() if self.webhook_at else None,
        }


# ---------------------------------------------------------------- хранение заказов
class ShopRepository(ABC):
    @abstractmethod
    def add(self, order: ShopOrder) -> None: ...

    @abstractmethod
    def update(self, order: ShopOrder) -> None: ...

    @abstractmethod
    def get(self, order_id: str) -> ShopOrder | None: ...

    @abstractmethod
    def get_by_invoice(self, invoice_id: str) -> ShopOrder | None: ...

    @abstractmethod
    def list_recent(self, limit: int = 20) -> list[ShopOrder]: ...


class ShopOrderRow(Base):
    __tablename__ = "shop_orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    items: Mapped[str] = mapped_column(Text)  # JSON
    total_wei: Mapped[str] = mapped_column(String(78))
    invoice_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    webhook_event: Mapped[str | None] = mapped_column(String(40), nullable=True)
    webhook_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


class SqlShopRepository(ShopRepository):
    def __init__(self, engine: Engine):
        Base.metadata.create_all(engine)  # создать таблицу shop_orders, если её нет
        self.session = sessionmaker(bind=engine, expire_on_commit=False)

    @staticmethod
    def _to_order(r: ShopOrderRow) -> ShopOrder:
        return ShopOrder(r.id, json.loads(r.items), int(r.total_wei), r.invoice_id, r.status,
                         _utc(r.created_at), r.webhook_event, _utc(r.webhook_at))

    def add(self, order: ShopOrder) -> None:
        with self.session.begin() as s:
            s.add(ShopOrderRow(id=order.id, items=json.dumps(order.items, ensure_ascii=False),
                               total_wei=str(order.total_wei), invoice_id=order.invoice_id, status=order.status,
                               created_at=order.created_at))

    def update(self, order: ShopOrder) -> None:
        with self.session.begin() as s:
            row = s.get(ShopOrderRow, order.id)
            row.status, row.webhook_event, row.webhook_at = order.status, order.webhook_event, order.webhook_at

    def get(self, order_id: str) -> ShopOrder | None:
        with self.session() as s:
            row = s.get(ShopOrderRow, order_id)
            return self._to_order(row) if row else None

    def get_by_invoice(self, invoice_id: str) -> ShopOrder | None:
        with self.session() as s:
            row = s.scalar(select(ShopOrderRow).where(ShopOrderRow.invoice_id == invoice_id))
            return self._to_order(row) if row else None

    def list_recent(self, limit: int = 20) -> list[ShopOrder]:
        with self.session() as s:
            rows = s.scalars(select(ShopOrderRow).order_by(ShopOrderRow.created_at.desc()).limit(limit))
            return [self._to_order(r) for r in rows]


# ---------------------------------------------------------------- логика магазина
class ShopError(Exception):
    pass


@dataclass
class DemoShop:
    orders: ShopRepository
    gateway: InvoiceService  # в настоящем магазине здесь был бы HTTP-клиент к POST /api/invoices
    webhook_secret: str
    ttl_minutes: int = 15
    clock: Clock = field(default=utc_now)

    def create_order(self, cart: dict[str, int]) -> ShopOrder:
        items, total = [], Decimal(0)
        for product_id, qty in cart.items():
            if qty <= 0:
                continue
            product = PRODUCTS.get(product_id)
            if product is None:
                raise ShopError(f"Товар '{product_id}' не найден")
            items.append({"product_id": product_id, "name": product["name"], "qty": qty,
                          "price_eth": product["price_eth"]})
            total += Decimal(product["price_eth"]) * qty
        if not items:
            raise ShopError("Корзина пуста")

        order_id = uuid.uuid4().hex
        description = "Кофейня: " + ", ".join(f"{i['name']} ×{i['qty']}" for i in items)
        invoice = self.gateway.create_invoice(total, description[:255], order_id=f"SHOP-{order_id[:6].upper()}",
                                              ttl_minutes=self.ttl_minutes)
        order = ShopOrder(order_id, items, eth_to_wei(total), invoice.id, "awaiting_payment", self.clock())
        self.orders.add(order)
        return order

    def handle_webhook(self, body: bytes, signature: str | None) -> ShopOrder | None:
        """Принять вебхук от шлюза. Без верной подписи — отказ (кто-то мог подделать запрос)."""
        expected = sign_webhook(body, self.webhook_secret)
        if not signature or not hmac.compare_digest(signature, expected):
            raise PermissionError("Неверная подпись вебхука")
        event = json.loads(body)
        order = self.orders.get_by_invoice(event["invoice"]["id"])
        if order is None:
            return None  # счёт создан не магазином (например, из кабинета) — игнорируем
        order.webhook_event = event["type"]
        order.webhook_at = self.clock()
        order.status = STATUS_BY_EVENT.get(event["type"], order.status)
        self.orders.update(order)
        return order


# ---------------------------------------------------------------- API магазина
router = APIRouter(prefix="/api/shop", tags=["Демо-магазин"])


class OrderRequest(BaseModel):
    items: dict[str, int] = Field(examples=[{"latte": 2, "croissant": 1}], description="id товара → количество")


def shop(request: Request) -> DemoShop:
    return request.app.state.services.shop


@router.get("/products")
def list_products():
    return [{"id": pid, **p} for pid, p in PRODUCTS.items()]


@router.post("/orders", status_code=201)
def create_order(body: OrderRequest, s: DemoShop = Depends(shop)):
    try:
        return s.create_order(body.items).to_dict()
    except ShopError as exc:
        raise HTTPException(422, str(exc))


@router.get("/orders")
def list_orders(s: DemoShop = Depends(shop)):
    return [o.to_dict() for o in s.orders.list_recent()]


@router.get("/orders/{order_id}")
def get_order(order_id: str, s: DemoShop = Depends(shop)):
    order = s.orders.get(order_id)
    if order is None:
        raise HTTPException(404, "Заказ не найден")
    return order.to_dict()


@router.post("/webhook", include_in_schema=True)
async def webhook(request: Request, s: DemoShop = Depends(shop)):
    """Сюда шлюз присылает вебхуки. Подпись X-Signature обязательна."""
    try:
        body = await request.body()
        order = await run_in_threadpool(s.handle_webhook, body, request.headers.get("X-Signature"))
    except PermissionError as exc:
        raise HTTPException(401, str(exc))
    return {"ok": True, "order_id": order.id if order else None}
