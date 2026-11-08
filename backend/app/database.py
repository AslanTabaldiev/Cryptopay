"""Хранение данных.

InvoiceRepository — интерфейс хранилища счетов, SqlInvoiceRepository — реализация на SQLAlchemy.
TimelineRepository — интерфейс хранилища хронологии, SqlTimelineRepository — реализация.
База: SQLite локально, PostgreSQL на Render. В тестах — заменители из tests/fakes.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.models import Invoice, InvoiceStatus, TimelineEntry, TransactionAlreadyUsed


class InvoiceRepository(ABC):
    @abstractmethod
    def add(self, invoice: Invoice) -> None: ...

    @abstractmethod
    def update(self, invoice: Invoice) -> None: ...

    @abstractmethod
    def get(self, invoice_id: str) -> Invoice | None: ...

    @abstractmethod
    def get_by_tx_hash(self, tx_hash: str) -> Invoice | None: ...

    @abstractmethod
    def list_recent(self, limit: int = 50) -> list[Invoice]: ...

    @abstractmethod
    def list_by_status(self, status: InvoiceStatus) -> list[Invoice]: ...


class TimelineRepository(ABC):
    @abstractmethod
    def add(self, entry: TimelineEntry) -> None: ...

    @abstractmethod
    def list_for(self, invoice_id: str) -> list[TimelineEntry]: ...


# ---------------------------------------------------------------- подключение
class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    """Подключение к базе. Таблицы создаются автоматически, если их ещё нет."""
    options = {"connect_args": {"check_same_thread": False}} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, pool_pre_ping=True, **options)
    Base.metadata.create_all(engine)
    return engine


# ---------------------------------------------------------------- таблицы


class InvoiceRow(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    amount_wei: Mapped[str] = mapped_column(String(78))  # число до 2^256 — храним строкой
    recipient: Mapped[str] = mapped_column(String(42))
    chain_id: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(255))
    order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tx_hash: Mapped[str | None] = mapped_column(String(66), unique=True, nullable=True)
    payer_address: Mapped[str | None] = mapped_column(String(42), nullable=True)
    tx_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmations: Mapped[int] = mapped_column(Integer, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TimelineRow(Base):
    __tablename__ = "invoice_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(String(32), index=True)
    type: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# Поля, которые копируются между Invoice и InvoiceRow как есть.
PLAIN_FIELDS = ["id", "recipient", "chain_id", "description", "order_id", "tx_hash", "payer_address",
                "confirmations", "failure_reason"]
DATE_FIELDS = ["created_at", "expires_at", "tx_submitted_at", "paid_at", "updated_at"]


def _utc(value: datetime | None) -> datetime | None:
    """SQLite теряет часовой пояс; всё в приложении хранится в UTC."""
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def to_row(invoice: Invoice, row: InvoiceRow) -> InvoiceRow:
    for name in PLAIN_FIELDS + DATE_FIELDS:
        setattr(row, name, getattr(invoice, name))
    row.amount_wei = str(invoice.amount_wei)
    row.status = invoice.status.value
    return row


def to_invoice(row: InvoiceRow) -> Invoice:
    values = {name: getattr(row, name) for name in PLAIN_FIELDS}
    values |= {name: _utc(getattr(row, name)) for name in DATE_FIELDS}
    return Invoice(**values, amount_wei=int(row.amount_wei), status=InvoiceStatus(row.status))


# ---------------------------------------------------------------- репозиторий
class SqlInvoiceRepository(InvoiceRepository):
    def __init__(self, engine: Engine):
        self.session = sessionmaker(bind=engine, expire_on_commit=False)

    def add(self, invoice: Invoice) -> None:
        with self.session.begin() as s:
            s.add(to_row(invoice, InvoiceRow()))

    def update(self, invoice: Invoice) -> None:
        try:
            with self.session.begin() as s:
                to_row(invoice, s.get(InvoiceRow, invoice.id))
        except IntegrityError as exc:
            # UNIQUE(tx_hash): одна транзакция не может оплатить два счёта
            raise TransactionAlreadyUsed(invoice.tx_hash or "") from exc

    def get(self, invoice_id: str) -> Invoice | None:
        with self.session() as s:
            row = s.get(InvoiceRow, invoice_id)
            return to_invoice(row) if row else None

    def get_by_tx_hash(self, tx_hash: str) -> Invoice | None:
        with self.session() as s:
            row = s.scalar(select(InvoiceRow).where(InvoiceRow.tx_hash == tx_hash.lower()))
            return to_invoice(row) if row else None

    def list_recent(self, limit: int = 50) -> list[Invoice]:
        with self.session() as s:
            rows = s.scalars(select(InvoiceRow).order_by(InvoiceRow.created_at.desc()).limit(limit))
            return [to_invoice(r) for r in rows]

    def list_by_status(self, status: InvoiceStatus) -> list[Invoice]:
        with self.session() as s:
            rows = s.scalars(select(InvoiceRow).where(InvoiceRow.status == status.value))
            return [to_invoice(r) for r in rows]


class SqlTimelineRepository(TimelineRepository):
    def __init__(self, engine: Engine):
        self.session = sessionmaker(bind=engine, expire_on_commit=False)

    def add(self, entry: TimelineEntry) -> None:
        with self.session.begin() as s:
            s.add(TimelineRow(invoice_id=entry.invoice_id, type=entry.type, message=entry.message,
                              created_at=entry.created_at))

    def list_for(self, invoice_id: str) -> list[TimelineEntry]:
        with self.session() as s:
            rows = s.scalars(select(TimelineRow).where(TimelineRow.invoice_id == invoice_id).order_by(TimelineRow.id))
            return [TimelineEntry(r.invoice_id, r.type, r.message, _utc(r.created_at)) for r in rows]
