from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.queries import (
    current_score,
    latest_score_subquery,
    ordered,
    score_detail,
    score_summary_from_row,
)
from app.api.schemas import (
    Band,
    Page,
    SortOrder,
    StoreDealSummary,
    StoreDetail,
    StoreListItem,
    StoreStats,
)

from app.models import (
    AccountStatus,
    Deal,
    DealStatus,
    EntityType,
    PaymentEvent,
    PaymentEventType,
    Store,
    Transaction,
)

router = APIRouter(prefix="/stores", tags=["stores"])

RECENT_DEALS_LIMIT = 10
StoreSortField = Literal["id", "name", "created_at", "fraud_score", "default_score"]


@router.get("", response_model=Page[StoreListItem])
def list_stores(
    q: str | None = Query(default=None, min_length=1, max_length=120,
                          description="Matches store name or commercial registration number"),
    category: str | None = Query(default=None, max_length=64),
    city: str | None = Query(default=None, max_length=64),
    account_status: AccountStatus | None = None,
    fraud_band: Band | None = None,
    default_band: Band | None = None,
    sort_by: StoreSortField = "id",
    order: SortOrder = "asc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    latest = latest_score_subquery(EntityType.STORE)
    join_on = latest.c.entity_id == Store.id

    conditions = []
    if q:
        pattern = f"%{q}%"
        conditions.append(or_(
            Store.name.ilike(pattern),
            Store.commercial_registration_no.ilike(pattern),
        ))
    if category is not None:
        conditions.append(Store.category == category)
    if city is not None:
        conditions.append(Store.city == city)
    if account_status is not None:
        conditions.append(Store.account_status == account_status)
    if fraud_band is not None:
        conditions.append(latest.c.fraud_band == fraud_band)
    if default_band is not None:
        conditions.append(latest.c.default_band == default_band)

    total = db.scalar(
        select(func.count(Store.id))
        .select_from(Store)
        .outerjoin(latest, join_on)
        .where(*conditions)
    )

    sort_columns = {
        "id": Store.id,
        "name": Store.name,
        "created_at": Store.created_at,
        "fraud_score": latest.c.fraud_score,
        "default_score": latest.c.default_score,
    }

    rows = db.execute(
        select(
            Store,
            latest.c.entity_id,
            latest.c.fraud_score,
            latest.c.default_score,
            latest.c.fraud_band,
            latest.c.default_band,
            latest.c.model_version,
            latest.c.computed_at,
        )
        .outerjoin(latest, join_on)
        .where(*conditions)
        .order_by(ordered(sort_columns[sort_by], order), Store.id)
        .limit(limit)
        .offset(offset)
    ).all()

    items = []
    for row in rows:
        store = row[0]
        items.append(StoreListItem(
            id=store.id,
            name=store.name,
            commercial_registration_no=store.commercial_registration_no,
            category=store.category,
            city=store.city,
            account_status=store.account_status,
            created_at=store.created_at,
            scores=score_summary_from_row(row._mapping, latest),
        ))

    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{store_id}", response_model=StoreDetail)
def get_store(store_id: int, db: Session = Depends(get_db)):
    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")

    total_deals, disputed_deals = db.execute(
        select(
            func.count(Deal.id),
            func.coalesce(
                func.sum(case((Deal.status == DealStatus.DISPUTED, 1), else_=0)), 0
            ),
        ).where(Deal.store_id == store_id)
    ).one()
        # Deals with at least one payment event (the "paid" denominator).
    paid_deals = db.scalar(
        select(func.count(func.distinct(Deal.id)))
        .select_from(Deal)
        .join(Transaction, Transaction.deal_id == Deal.id)
        .join(PaymentEvent, PaymentEvent.transaction_id == Transaction.id)
        .where(Deal.store_id == store_id)
    ) or 0

    # Of those, deals with a refund event.
    refunded_deals = db.scalar(
        select(func.count(func.distinct(Deal.id)))
        .select_from(Deal)
        .join(Transaction, Transaction.deal_id == Deal.id)
        .join(PaymentEvent, PaymentEvent.transaction_id == Transaction.id)
        .where(
            Deal.store_id == store_id,
            PaymentEvent.event_type == PaymentEventType.REFUND,
        )
    ) or 0
    recent = db.scalars(
        select(Deal)
        .where(Deal.store_id == store_id)
        .order_by(Deal.created_at.desc(), Deal.id.desc())
        .limit(RECENT_DEALS_LIMIT)
    ).all()

    return StoreDetail(
        id=store.id,
        name=store.name,
        commercial_registration_no=store.commercial_registration_no,
        category=store.category,
        city=store.city,
        account_status=store.account_status,
        created_at=store.created_at,
        scores=score_detail(current_score(db, EntityType.STORE, store_id)),
        stats=StoreStats(
            total_deals=total_deals,
            disputed_deals=int(disputed_deals),
            dispute_rate=round(disputed_deals / total_deals, 4) if total_deals else None,
            paid_deals=paid_deals,
            refunded_deals=refunded_deals,
            refund_rate=round(refunded_deals / paid_deals, 4) if paid_deals else None,
        ),
        recent_deals=[
            StoreDealSummary(
                id=deal.id,
                customer_id=deal.customer_id,
                amount_sar=float(deal.amount_sar),
                status=deal.status,
                created_at=deal.created_at,
                closed_at=deal.closed_at,
            )
            for deal in recent
        ],
    )