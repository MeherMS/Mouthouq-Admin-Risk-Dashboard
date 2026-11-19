from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas import Page
from app.models import Customer, Deal, PaymentEvent, Store, Transaction

router = APIRouter(tags=["transaction timeline"])


class PaymentEventItem(BaseModel):
    id: int
    event_type: str
    occurred_at: datetime


class TransactionTimelineItem(BaseModel):
    id: int
    deal_id: int
    amount_sar: float
    method: str
    status: str
    timestamp: datetime
    failure_reason: str | None
    events: list[PaymentEventItem]


def _val(value) -> str:
    # Enums come back as enum members; the API returns their string values.
    return value.value if hasattr(value, "value") else str(value)


def _timeline(db: Session, deal_filter, limit: int, offset: int) -> Page[TransactionTimelineItem]:
    base = select(Transaction).join(Deal, Deal.id == Transaction.deal_id).where(deal_filter)

    total = db.scalar(
        select(func.count(Transaction.id))
        .join(Deal, Deal.id == Transaction.deal_id)
        .where(deal_filter)
    ) or 0

    transactions = db.scalars(
        base.order_by(Transaction.timestamp.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    # Load all events for these transactions in one query.
    ids = [t.id for t in transactions]
    events_by_txn: dict[int, list[PaymentEventItem]] = {tid: [] for tid in ids}
    if ids:
        events = db.scalars(
            select(PaymentEvent)
            .where(PaymentEvent.transaction_id.in_(ids))
            .order_by(PaymentEvent.occurred_at, PaymentEvent.id)
        ).all()
        for e in events:
            events_by_txn[e.transaction_id].append(PaymentEventItem(
                id=e.id,
                event_type=_val(e.event_type),
                occurred_at=e.occurred_at,
            ))

    items = [
        TransactionTimelineItem(
            id=t.id,
            deal_id=t.deal_id,
            amount_sar=float(t.amount_sar),
            method=_val(t.method),
            status=_val(t.status),
            timestamp=t.timestamp,
            failure_reason=t.failure_reason,
            events=events_by_txn.get(t.id, []),
        )
        for t in transactions
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/customers/{customer_id}/transactions", response_model=Page[TransactionTimelineItem])
def customer_transactions(
    customer_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if db.get(Customer, customer_id) is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return _timeline(db, Deal.customer_id == customer_id, limit, offset)


@router.get("/stores/{store_id}/transactions", response_model=Page[TransactionTimelineItem])
def store_transactions(
    store_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if db.get(Store, store_id) is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return _timeline(db, Deal.store_id == store_id, limit, offset)