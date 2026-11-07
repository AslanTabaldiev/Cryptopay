"""Adapter: InvoiceRepository on SQLAlchemy (SQLite locally, PostgreSQL in the cloud)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.domain.errors import TransactionAlreadyUsed
from app.domain.invoice import Invoice, InvoiceStatus
from app.ports.repository import InvoiceRepository


class Base(DeclarativeBase):
    pass


class InvoiceRow(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    amount_wei: Mapped[str] = mapped_column(String(78))  # uint256 does not fit in BIGINT
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


def _utc(value: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; everything in the app is UTC, so restore it."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _to_row(invoice: Invoice, row: InvoiceRow | None = None) -> InvoiceRow:
    row = row or InvoiceRow(id=invoice.id)
    row.amount_wei = str(invoice.amount_wei)
    row.recipient = invoice.recipient
    row.chain_id = invoice.chain_id
    row.description = invoice.description
    row.order_id = invoice.order_id
    row.status = invoice.status.value
    row.created_at = invoice.created_at
    row.expires_at = invoice.expires_at
    row.tx_hash = invoice.tx_hash
    row.payer_address = invoice.payer_address
    row.tx_submitted_at = invoice.tx_submitted_at
    row.confirmations = invoice.confirmations
    row.failure_reason = invoice.failure_reason
    row.paid_at = invoice.paid_at
    row.updated_at = invoice.updated_at
    return row


def _to_entity(row: InvoiceRow) -> Invoice:
    return Invoice(
        id=row.id,
        amount_wei=int(row.amount_wei),
        recipient=row.recipient,
        chain_id=row.chain_id,
        description=row.description,
        order_id=row.order_id,
        status=InvoiceStatus(row.status),
        created_at=_utc(row.created_at),
        expires_at=_utc(row.expires_at),
        tx_hash=row.tx_hash,
        payer_address=row.payer_address,
        tx_submitted_at=_utc(row.tx_submitted_at),
        confirmations=row.confirmations or 0,
        failure_reason=row.failure_reason,
        paid_at=_utc(row.paid_at),
        updated_at=_utc(row.updated_at),
    )


def create_db_engine(database_url: str) -> Engine:
    kwargs = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(database_url, **kwargs)
    Base.metadata.create_all(engine)
    return engine


class SqlAlchemyInvoiceRepository(InvoiceRepository):
    def __init__(self, engine: Engine):
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def add(self, invoice: Invoice) -> None:
        with self._sessions.begin() as session:
            session.add(_to_row(invoice))

    def update(self, invoice: Invoice) -> None:
        try:
            with self._sessions.begin() as session:
                row = session.get(InvoiceRow, invoice.id)
                if row is None:
                    raise KeyError(invoice.id)
                _to_row(invoice, row)
        except IntegrityError as exc:
            # UNIQUE(tx_hash) is the last line of defence against two concurrent
            # requests attaching the same transaction to different invoices.
            raise TransactionAlreadyUsed(invoice.tx_hash or "") from exc

    def get(self, invoice_id: str) -> Invoice | None:
        with self._sessions() as session:
            row = session.get(InvoiceRow, invoice_id)
            return _to_entity(row) if row else None

    def get_by_tx_hash(self, tx_hash: str) -> Invoice | None:
        with self._sessions() as session:
            row = session.scalar(select(InvoiceRow).where(InvoiceRow.tx_hash == tx_hash.lower()))
            return _to_entity(row) if row else None

    def list_recent(self, limit: int = 50) -> list[Invoice]:
        with self._sessions() as session:
            rows = session.scalars(select(InvoiceRow).order_by(InvoiceRow.created_at.desc()).limit(limit))
            return [_to_entity(r) for r in rows]

    def list_by_status(self, status: InvoiceStatus) -> list[Invoice]:
        with self._sessions() as session:
            rows = session.scalars(select(InvoiceRow).where(InvoiceRow.status == status.value))
            return [_to_entity(r) for r in rows]
