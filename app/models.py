import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enum_values(enum_cls):
    """Store the enum's value (e.g. 'on_time') in the DB, not its name (ON_TIME)."""
    return [member.value for member in enum_cls]


# ---------- Enums ----------

class AccountStatus(str, enum.Enum):
    ACTIVE = "active"
    PENDING = "pending"
    FROZEN = "frozen"
    REJECTED = "rejected"


class DealStatus(str, enum.Enum):
    OPENED = "opened"
    PAID = "paid"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class PaymentMethod(str, enum.Enum):
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    INSTALLMENT = "installment"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PaymentEventType(str, enum.Enum):
    ON_TIME = "on_time"
    LATE = "late"
    MISSED = "missed"
    PARTIAL = "partial"
    CHARGEBACK = "chargeback"
    REFUND = "refund"


class EntityType(str, enum.Enum):
    CUSTOMER = "customer"
    STORE = "store"


class ActionType(str, enum.Enum):
    FREEZE = "freeze"
    UNFREEZE = "unfreeze"
    APPROVE = "approve"
    REJECT = "reject"
    FLAG_REVIEW = "flag_review"
    ADD_NOTE = "add_note"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    VIEWER = "viewer"


def _enum(cls, name):
    return Enum(
        cls,
        name=name,
        native_enum=False,
        values_callable=enum_values,
        validate_strings=True,
        length=32,
    )


# ---------- Tables ----------

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    national_id_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(32), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    city: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    account_status: Mapped[AccountStatus] = mapped_column(
        _enum(AccountStatus, "account_status"), default=AccountStatus.ACTIVE
    )

    # ADDED: synthetic-only ground truth. Remove or isolate before real data.
    synthetic_profile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    default_label: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    deals: Mapped[list["Deal"]] = relationship(back_populates="customer")


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    commercial_registration_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    city: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    account_status: Mapped[AccountStatus] = mapped_column(
        _enum(AccountStatus, "account_status"), default=AccountStatus.PENDING
    )

    deals: Mapped[list["Deal"]] = relationship(back_populates="store")


class Deal(Base):
    __tablename__ = "deals"
    __table_args__ = (
        Index("ix_deals_customer_created", "customer_id", "created_at"),
        Index("ix_deals_store_created", "store_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    amount_sar: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[DealStatus] = mapped_column(_enum(DealStatus, "deal_status"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ADDED: synthetic-only fraud ground truth from the generator's fraud-actor process.
    is_fraud: Mapped[bool] = mapped_column(Boolean, default=False)

    customer: Mapped[Customer] = relationship(back_populates="deals")
    store: Mapped[Store] = relationship(back_populates="deals")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="deal")

class Shipment(Base):
    """One physical delivery per deal (physical-category stores only).

    final_status: 'delivered' or 'rto' (return to origin).
    failure_reason: 'address_not_found', 'recipient_unavailable',
                    'refused_by_customer', or None when delivered first try.
    store_claimed_delivered: True when the store marked it delivered but the
                    shipment was not (synthetic fake-delivery case).
    """
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deal_id: Mapped[int] = mapped_column(
        ForeignKey("deals.id"), unique=True, index=True
    )
    origin_city: Mapped[str] = mapped_column(String(32))
    destination_city: Mapped[str] = mapped_column(String(32))
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer)
    final_status: Mapped[str] = mapped_column(String(16), index=True)
    failure_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    store_claimed_delivered: Mapped[bool] = mapped_column(Boolean, default=False)

    deal: Mapped[Deal] = relationship()


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id"), index=True)
    amount_sar: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[PaymentMethod] = mapped_column(_enum(PaymentMethod, "payment_method"))
    status: Mapped[TransactionStatus] = mapped_column(_enum(TransactionStatus, "transaction_status"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    deal: Mapped[Deal] = relationship(back_populates="transactions")
    payment_events: Mapped[list["PaymentEvent"]] = relationship(back_populates="transaction")


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), index=True)
    event_type: Mapped[PaymentEventType] = mapped_column(_enum(PaymentEventType, "payment_event_type"))
    # ADDED: needed to compute late-payment trends over time.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    transaction: Mapped[Transaction] = relationship(back_populates="payment_events")


class RiskScore(Base):
    """
    Score history: one row per entity per model run.
    entity_id has no foreign key because it points to customers or stores
    depending on entity_type.
    """
    __tablename__ = "risk_scores"
    __table_args__ = (
        Index("ix_risk_scores_entity_time", "entity_type", "entity_id", "computed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[EntityType] = mapped_column(_enum(EntityType, "entity_type"))
    entity_id: Mapped[int] = mapped_column(Integer)
    fraud_score: Mapped[float] = mapped_column(Float)      # 0 to 100
    default_score: Mapped[float] = mapped_column(Float)    # 0 to 100
    fraud_band: Mapped[str] = mapped_column(String(8))     # low / medium / high
    default_band: Mapped[str] = mapped_column(String(8))
    model_version: Mapped[str] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    top_factors: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Action(Base):
    __tablename__ = "actions"
    __table_args__ = (
        Index("ix_actions_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[EntityType] = mapped_column(_enum(EntityType, "entity_type"))
    entity_id: Mapped[int] = mapped_column(Integer)
    action_type: Mapped[ActionType] = mapped_column(_enum(ActionType, "action_type"))
    reason: Mapped[str] = mapped_column(Text)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    """Append-only. The application should only ever INSERT into this table."""
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    event: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(_enum(UserRole, "user_role"))


class ShipmentPrediction(Base):
    """Shipment-level predictions. No foreign key, same pattern as risk_scores."""
    __tablename__ = "shipment_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(Integer, index=True)
    delivery_success_pct: Mapped[float] = mapped_column(Float)
    expected_days: Mapped[float] = mapped_column(Float)
    reason_if_failed: Mapped[str] = mapped_column(String(32))
    reason_prob_pct: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(64), index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))