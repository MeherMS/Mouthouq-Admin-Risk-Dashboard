from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routers.action_log import ActionLogItem
from app.api.schemas import Page
from app.models import Action, Customer, EntityType, Store

router = APIRouter(tags=["action history"])


def _history(db: Session, entity_type: EntityType, entity_id: int,
             limit: int, offset: int) -> Page[ActionLogItem]:
    conditions = [
        Action.entity_type == entity_type,
        Action.entity_id == entity_id,
    ]

    total = db.scalar(select(func.count(Action.id)).where(*conditions)) or 0

    rows = db.scalars(
        select(Action)
        .where(*conditions)
        .order_by(Action.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    items = [
        ActionLogItem(
            id=a.id,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            action_type=a.action_type,
            reason=a.reason,
            admin_id=a.admin_id,
            created_at=a.created_at,
        )
        for a in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/customers/{customer_id}/actions", response_model=Page[ActionLogItem])
def customer_history(
    customer_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if db.get(Customer, customer_id) is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return _history(db, EntityType.CUSTOMER, customer_id, limit, offset)


@router.get("/stores/{store_id}/actions", response_model=Page[ActionLogItem])
def store_history(
    store_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if db.get(Store, store_id) is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return _history(db, EntityType.STORE, store_id, limit, offset)