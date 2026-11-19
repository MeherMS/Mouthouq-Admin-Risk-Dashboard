from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models import AccountStatus, ActionType, EntityType


class ReasonBody(BaseModel):
    reason: str = Field(
        min_length=3,
        max_length=2000,
        description="Required. Stored in the action log and audit trail.",
    )

    @field_validator("reason")
    @classmethod
    def trim_and_check(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("reason must be at least 3 characters after trimming")
        return value


class ActionResult(BaseModel):
    changed: bool
    entity_type: EntityType
    entity_id: int
    action_type: ActionType
    account_status: AccountStatus | None
    action_id: int | None
    created_at: datetime | None