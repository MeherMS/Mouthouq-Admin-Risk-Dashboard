from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.schemas import Page
from app.models import Action, ActionType, EntityType

router = APIRouter(prefix="/actions", tags=["action log"])


class ActionLogItem(BaseModel):
    id: int
    entity_type: EntityType
    entity_id: int
    action_type: ActionType
    reason: str
    admin_id: int | None
    created_at: datetime


@router.get("", response_model=Page[ActionLogItem])
def list_actions(
    entity_type: EntityType | None = None,
    entity_id: int | None = None,
    action_type: ActionType | None = None,
    admin_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    conditions = []
    if entity_type is not None:
        conditions.append(Action.entity_type == entity_type)
    if entity_id is not None:
        conditions.append(Action.entity_id == entity_id)
    if action_type is not None:
        conditions.append(Action.action_type == action_type)
    if admin_id is not None:
        conditions.append(Action.admin_id == admin_id)

    total = db.scalar(
        select(func.count(Action.id)).where(*conditions)
    )

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