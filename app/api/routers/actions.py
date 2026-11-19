from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.action_schemas import ActionResult, ReasonBody
from app.api.action_service import Outcome, apply_action
from app.api.deps import get_db
from app.api.security import get_current_admin
from app.models import ActionType, EntityType, User

customer_actions = APIRouter(prefix="/customers", tags=["customer actions"])
store_actions = APIRouter(prefix="/stores", tags=["store actions"])


def _run(
    db: Session,
    admin: User,
    entity_type: EntityType,
    entity_id: int,
    action_type: ActionType,
    body: ReasonBody,
) -> ActionResult:
    outcome: Outcome = apply_action(
        db, admin, entity_type, entity_id, action_type, body.reason
    )
    return ActionResult(
        changed=outcome.changed,
        entity_type=entity_type,
        entity_id=entity_id,
        action_type=action_type,
        account_status=outcome.account_status,
        action_id=outcome.action.id if outcome.action else None,
        created_at=outcome.action.created_at if outcome.action else None,
    )


# ---------- Customers ----------

@customer_actions.post("/{customer_id}/freeze", response_model=ActionResult)
def freeze_customer(
    customer_id: int,
    body: ReasonBody,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _run(db, admin, EntityType.CUSTOMER, customer_id, ActionType.FREEZE, body)


@customer_actions.post("/{customer_id}/unfreeze", response_model=ActionResult)
def unfreeze_customer(
    customer_id: int,
    body: ReasonBody,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _run(db, admin, EntityType.CUSTOMER, customer_id, ActionType.UNFREEZE, body)


@customer_actions.post("/{customer_id}/flag-review", response_model=ActionResult)
def flag_customer(
    customer_id: int,
    body: ReasonBody,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _run(db, admin, EntityType.CUSTOMER, customer_id, ActionType.FLAG_REVIEW, body)


@customer_actions.post("/{customer_id}/notes", response_model=ActionResult)
def add_customer_note(
    customer_id: int,
    body: ReasonBody,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _run(db, admin, EntityType.CUSTOMER, customer_id, ActionType.ADD_NOTE, body)


# ---------- Stores ----------

@store_actions.post("/{store_id}/approve", response_model=ActionResult)
def approve_store(
    store_id: int,
    body: ReasonBody,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _run(db, admin, EntityType.STORE, store_id, ActionType.APPROVE, body)


@store_actions.post("/{store_id}/reject", response_model=ActionResult)
def reject_store(
    store_id: int,
    body: ReasonBody,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _run(db, admin, EntityType.STORE, store_id, ActionType.REJECT, body)


@store_actions.post("/{store_id}/flag-review", response_model=ActionResult)
def flag_store(
    store_id: int,
    body: ReasonBody,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _run(db, admin, EntityType.STORE, store_id, ActionType.FLAG_REVIEW, body)


@store_actions.post("/{store_id}/notes", response_model=ActionResult)
def add_store_note(
    store_id: int,
    body: ReasonBody,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _run(db, admin, EntityType.STORE, store_id, ActionType.ADD_NOTE, body)