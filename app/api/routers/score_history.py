from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Customer, EntityType, RiskScore, Store

router = APIRouter(prefix="/scores", tags=["score history"])


class ScorePoint(BaseModel):
    id: int
    computed_at: datetime
    fraud_score: float
    default_score: float
    fraud_band: str
    default_band: str
    model_version: str


class ScoreHistory(BaseModel):
    entity_type: EntityType
    entity_id: int
    points: list[ScorePoint]


@router.get("/history/{entity_type}/{entity_id}", response_model=ScoreHistory)
def score_history(
    entity_type: EntityType,
    entity_id: int,
    limit: int = Query(default=365, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    model = Customer if entity_type == EntityType.CUSTOMER else Store
    if db.get(model, entity_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"{entity_type.value.capitalize()} not found",
        )

    # Take the most recent rows, then return them oldest first for charting.
    rows = db.scalars(
        select(RiskScore)
        .where(
            RiskScore.entity_type == entity_type,
            RiskScore.entity_id == entity_id,
        )
        .order_by(RiskScore.computed_at.desc(), RiskScore.id.desc())
        .limit(limit)
    ).all()

    points = [
        ScorePoint(
            id=r.id,
            computed_at=r.computed_at,
            fraud_score=float(r.fraud_score),
            default_score=float(r.default_score),
            fraud_band=r.fraud_band,
            default_band=r.default_band,
            model_version=r.model_version,
        )
        for r in reversed(rows)
    ]

    return ScoreHistory(entity_type=entity_type, entity_id=entity_id, points=points)