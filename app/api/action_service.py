from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AccountStatus,
    Action,
    ActionType,
    AuditLog,
    Customer,
    EntityType,
    Store,
    User,
)

# Status rules per entity and action:
#   action -> (target status, required current status or None)
# A required current status of None means the action is allowed from any state.
STATUS_RULES = {
    EntityType.CUSTOMER: {
        ActionType.FREEZE: (AccountStatus.FROZEN, None),
        ActionType.UNFREEZE: (AccountStatus.ACTIVE, AccountStatus.FROZEN),
    },
    EntityType.STORE: {
        ActionType.APPROVE: (AccountStatus.ACTIVE, None),
        ActionType.REJECT: (AccountStatus.REJECTED, None),
    },
}


@dataclass
class Outcome:
    changed: bool
    action: Action | None
    account_status: AccountStatus | None


def _load_entity(db: Session, entity_type: EntityType, entity_id: int):
    model = Customer if entity_type == EntityType.CUSTOMER else Store
    entity = db.get(model, entity_id)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail=f"{entity_type.value.capitalize()} not found",
        )
    return entity


def _last_action_type(db: Session, entity_type: EntityType, entity_id: int):
    return db.scalars(
        select(Action.action_type)
        .where(Action.entity_type == entity_type, Action.entity_id == entity_id)
        .order_by(Action.id.desc())
        .limit(1)
    ).first()


def apply_action(
    db: Session,
    admin: User,
    entity_type: EntityType,
    entity_id: int,
    action_type: ActionType,
    reason: str,
) -> Outcome:
    entity = _load_entity(db, entity_type, entity_id)
    status_before = entity.account_status

    # 1. Status-changing actions
    target_status = None
    rules = STATUS_RULES[entity_type].get(action_type)
    if rules is not None:
        target, required_current = rules
        if status_before == target:
            # Already in the requested state: success, no new rows.
            return Outcome(changed=False, action=None, account_status=status_before)
        if required_current is not None and status_before != required_current:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot {action_type.value}: current status is "
                    f"{status_before.value}, expected {required_current.value}"
                ),
            )
        target_status = target

    # 2. Flag review: skip if the most recent action is already a flag
    if action_type == ActionType.FLAG_REVIEW:
        last = _last_action_type(db, entity_type, entity_id)
        if last == ActionType.FLAG_REVIEW:
            return Outcome(changed=False, action=None, account_status=status_before)

    # 3. Notes always create a row (each note is distinct).
    if target_status is not None:
        entity.account_status = target_status

    action = Action(
        entity_type=entity_type,
        entity_id=entity_id,
        action_type=action_type,
        reason=reason,
        admin_id=admin.id,
    )
    db.add(action)
    db.flush()  # assigns action.id and created_at

    db.add(AuditLog(
        admin_id=admin.id,
        event=f"{entity_type.value}.{action_type.value}",
        payload={
            "entity_type": entity_type.value,
            "entity_id": entity_id,
            "action_id": action.id,
            "reason": reason,
            "status_before": status_before.value,
            "status_after": entity.account_status.value,
        },
    ))

    db.commit()
    return Outcome(changed=True, action=action, account_status=entity.account_status)