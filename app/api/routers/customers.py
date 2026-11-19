from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
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
    CustomerDealSummary,
    CustomerDetail,
    CustomerListItem,
    Page,
    SortOrder,
)
from app.models import AccountStatus, Customer, Deal, EntityType, Store

router = APIRouter(prefix="/customers", tags=["customers"])

RECENT_DEALS_LIMIT = 10
CustomerSortField = Literal["id", "name", "created_at", "fraud_score", "default_score"]


@router.get("", response_model=Page[CustomerListItem])
def list_customers(
    q: str | None = Query(default=None, min_length=1, max_length=120,
                          description="Matches name, phone or email"),
    account_status: AccountStatus | None = None,
    fraud_band: Band | None = None,
    default_band: Band | None = None,
    sort_by: CustomerSortField = "id",
    order: SortOrder = "asc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    latest = latest_score_subquery(EntityType.CUSTOMER)
    join_on = latest.c.entity_id == Customer.id

    conditions = []
    if q:
        pattern = f"%{q}%"
        conditions.append(or_(
            Customer.name.ilike(pattern),
            Customer.phone.ilike(pattern),
            Customer.email.ilike(pattern),
        ))
    if account_status is not None:
        conditions.append(Customer.account_status == account_status)
    if fraud_band is not None:
        conditions.append(latest.c.fraud_band == fraud_band)
    if default_band is not None:
        conditions.append(latest.c.default_band == default_band)

    total = db.scalar(
        select(func.count(Customer.id))
        .select_from(Customer)
        .outerjoin(latest, join_on)
        .where(*conditions)
    )

    sort_columns = {
        "id": Customer.id,
        "name": Customer.name,
        "created_at": Customer.created_at,
        "fraud_score": latest.c.fraud_score,
        "default_score": latest.c.default_score,
    }

    rows = db.execute(
        select(
            Customer,
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
        .order_by(ordered(sort_columns[sort_by], order), Customer.id)
        .limit(limit)
        .offset(offset)
    ).all()

    items = []
    for row in rows:
        customer = row[0]
        items.append(CustomerListItem(
            id=customer.id,
            name=customer.name,
            phone=customer.phone,
            email=customer.email,
            account_status=customer.account_status,
            created_at=customer.created_at,
            scores=score_summary_from_row(row._mapping, latest),
        ))

    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{customer_id}", response_model=CustomerDetail)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    deal_rows = db.execute(
        select(Deal, Store.name)
        .join(Store, Store.id == Deal.store_id)
        .where(Deal.customer_id == customer_id)
        .order_by(Deal.created_at.desc(), Deal.id.desc())
        .limit(RECENT_DEALS_LIMIT)
    ).all()

    return CustomerDetail(
        id=customer.id,
        name=customer.name,
        phone=customer.phone,
        email=customer.email,
        account_status=customer.account_status,
        created_at=customer.created_at,
        scores=score_detail(current_score(db, EntityType.CUSTOMER, customer_id)),
        recent_deals=[
            CustomerDealSummary(
                id=deal.id,
                store_id=deal.store_id,
                store_name=store_name,
                amount_sar=float(deal.amount_sar),
                status=deal.status,
                created_at=deal.created_at,
                closed_at=deal.closed_at,
            )
            for deal, store_name in deal_rows
        ],
    )