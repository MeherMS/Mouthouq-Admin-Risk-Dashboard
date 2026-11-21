from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.queries import latest_score_subquery
from app.models import Customer, EntityType, RiskScore, Store

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

TOP_LIMIT = 10


class RiskBreakdown(BaseModel):
    low: int
    medium: int
    high: int
    unscored: int


class EntityRiskCounts(BaseModel):
    total: int
    fraud: RiskBreakdown
    default: RiskBreakdown


class TrendPoint(BaseModel):
    date: str
    fraud_high: int
    default_high: int


class TopEntity(BaseModel):
    entity_type: EntityType
    entity_id: int
    name: str
    account_status: str
    fraud_score: float
    fraud_band: str
    default_score: float
    default_band: str


class DashboardSummary(BaseModel):
    customers: EntityRiskCounts
    stores: EntityRiskCounts
    trend: list[TrendPoint]
    top_fraud: list[TopEntity]     # ranked by fraud score (absolute, 0-100)
    top_default: list[TopEntity]   # ranked by default percentile (0-100)
    model_version: str | None
    computed_at: datetime | None


def _breakdown(db: Session, latest, band_column, total: int) -> RiskBreakdown:
    rows = db.execute(
        select(band_column, func.count())
        .select_from(latest)
        .group_by(band_column)
    ).all()
    found = {band: count for band, count in rows}
    scored = sum(found.values())
    return RiskBreakdown(
        low=found.get("low", 0),
        medium=found.get("medium", 0),
        high=found.get("high", 0),
        unscored=total - scored,
    )


def _entity_counts(db: Session, entity_type: EntityType) -> EntityRiskCounts:
    model = Customer if entity_type == EntityType.CUSTOMER else Store
    total = db.scalar(select(func.count(model.id))) or 0
    latest = latest_score_subquery(entity_type)
    return EntityRiskCounts(
        total=total,
        fraud=_breakdown(db, latest, latest.c.fraud_band, total),
        default=_breakdown(db, latest, latest.c.default_band, total),
    )


def _top_entities(db: Session, entity_type: EntityType, limit: int, risk: str) -> list[TopEntity]:
    """Top entities of one type, ordered by one risk score only."""
    model = Customer if entity_type == EntityType.CUSTOMER else Store
    latest = latest_score_subquery(entity_type)
    sort_column = latest.c.fraud_score if risk == "fraud" else latest.c.default_score
    rows = db.execute(
        select(
            model.id.label("id"),
            model.name.label("name"),
            model.account_status.label("account_status"),
            latest.c.fraud_score,
            latest.c.fraud_band,
            latest.c.default_score,
            latest.c.default_band,
        )
        .select_from(model)
        .join(latest, latest.c.entity_id == model.id)
        .order_by(sort_column.desc(), model.id)
        .limit(limit)
    ).all()

    return [
        TopEntity(
            entity_type=entity_type,
            entity_id=r.id,
            name=r.name,
            account_status=r.account_status.value,
            fraud_score=float(r.fraud_score),
            fraud_band=r.fraud_band,
            default_score=float(r.default_score),
            default_band=r.default_band,
        )
        for r in rows
    ]


def _top_list(db: Session, risk: str) -> list[TopEntity]:
    """Customers and stores merged, ranked on one risk score only."""
    merged = (
        _top_entities(db, EntityType.CUSTOMER, TOP_LIMIT, risk)
        + _top_entities(db, EntityType.STORE, TOP_LIMIT, risk)
    )
    attr = "fraud_score" if risk == "fraud" else "default_score"
    merged.sort(key=lambda e: (-getattr(e, attr), e.entity_id))
    return merged[:TOP_LIMIT]


def _trend(db: Session) -> list[TrendPoint]:
    # func.date() returns a plain 'YYYY-MM-DD' string on SQLite.
    # Using no SQLAlchemy type here avoids the Date result processor that failed.
    day = func.date(RiskScore.computed_at)
    rows = db.execute(
        select(
            day.label("day"),
            func.sum(case((RiskScore.fraud_band == "high", 1), else_=0)).label("fraud_high"),
            func.sum(case((RiskScore.default_band == "high", 1), else_=0)).label("default_high"),
        )
        .group_by(day)
        .order_by(day)
    ).all()

    return [
        TrendPoint(
            date=str(r.day),
            fraud_high=int(r.fraud_high or 0),
            default_high=int(r.default_high or 0),
        )
        for r in rows
    ]


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(db: Session = Depends(get_db)):
    latest_row = db.execute(
        select(RiskScore.model_version, RiskScore.computed_at)
        .order_by(RiskScore.id.desc())
        .limit(1)
    ).first()

    return DashboardSummary(
        customers=_entity_counts(db, EntityType.CUSTOMER),
        stores=_entity_counts(db, EntityType.STORE),
        trend=_trend(db),
        top_fraud=_top_list(db, "fraud"),
        top_default=_top_list(db, "default"),
        model_version=latest_row.model_version if latest_row else None,
        computed_at=latest_row.computed_at if latest_row else None,
    )