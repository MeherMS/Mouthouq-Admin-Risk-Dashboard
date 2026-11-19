from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import ScoreDetail, ScoreSummary, SortOrder
from app.models import EntityType, RiskScore


def latest_score_subquery(entity_type: EntityType):
    """
    One row per entity: the most recent risk_scores row for that entity.
    Uses the highest id as the "latest" marker, which is safe because ids
    grow with each insert.
    """
    latest_ids = (
        select(func.max(RiskScore.id).label("max_id"))
        .where(RiskScore.entity_type == entity_type)
        .group_by(RiskScore.entity_id)
        .subquery()
    )
    return (
        select(RiskScore)
        .join(latest_ids, RiskScore.id == latest_ids.c.max_id)
        .subquery("latest_scores")
    )


def score_summary_from_row(mapping, latest) -> ScoreSummary | None:
    """Build a score summary from a joined row. Returns None if the entity has no score."""
    if mapping[latest.c.entity_id] is None:
        return None
    return ScoreSummary(
        fraud_score=mapping[latest.c.fraud_score],
        default_score=mapping[latest.c.default_score],
        fraud_band=mapping[latest.c.fraud_band],
        default_band=mapping[latest.c.default_band],
        model_version=mapping[latest.c.model_version],
        computed_at=mapping[latest.c.computed_at],
    )


def current_score(db: Session, entity_type: EntityType, entity_id: int) -> RiskScore | None:
    return db.scalars(
        select(RiskScore)
        .where(RiskScore.entity_type == entity_type, RiskScore.entity_id == entity_id)
        .order_by(RiskScore.id.desc())
        .limit(1)
    ).first()


def score_detail(score: RiskScore | None) -> ScoreDetail | None:
    if score is None:
        return None
    return ScoreDetail(
        fraud_score=score.fraud_score,
        default_score=score.default_score,
        fraud_band=score.fraud_band,
        default_band=score.default_band,
        model_version=score.model_version,
        computed_at=score.computed_at,
        top_factors=score.top_factors,
    )


def ordered(column, order: SortOrder):
    """Sort with NULLs last, so unscored entities don't crowd the top of a score sort."""
    if order == "desc":
        return column.desc().nulls_last()
    return column.asc().nulls_last()