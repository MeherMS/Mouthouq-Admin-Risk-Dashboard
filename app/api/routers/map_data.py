"""Map endpoints: city-level points and shipment flows. Read-only."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.geo import city_point
from app.geo import CITY_CENTERS
from app.models import Customer, RiskScore, Shipment, Store

router = APIRouter(prefix="/map", tags=["map"])


def _latest_customer_scores(db: Session) -> dict:
    """Latest risk_scores row per customer, keyed by customer id."""
    latest_ids = (
        select(func.max(RiskScore.id))
        .where(RiskScore.entity_type == "customer")
        .group_by(RiskScore.entity_id)
    )
    rows = db.execute(
        select(RiskScore).where(RiskScore.id.in_(latest_ids))
    ).scalars().all()
    return {r.entity_id: r for r in rows}


@router.get("/points")
def map_points(
    entity: str = Query("customer", pattern="^(customer|store)$"),
    db: Session = Depends(get_db),
):
    if entity == "customer":
        rows = db.execute(select(Customer.id, Customer.city)).all()
        scores = _latest_customer_scores(db)
    else:
        # Store scores are not built yet, so store points carry no bands.
        rows = db.execute(select(Store.id, Store.city)).all()
        scores = {}

    points = []
    for entity_id, city in rows:
        lat, lon = city_point(city, f"{entity}:{entity_id}")
        s = scores.get(entity_id)
        points.append({
            "entity_type": entity,
            "entity_id": entity_id,
            "city": city,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "fraud_band": s.fraud_band if s else None,
            "default_band": s.default_band if s else None,
            "model_version": s.model_version if s else None,
        })

    return {"count": len(points), "points": points}


@router.get("/shipment-flows")
def shipment_flows(db: Session = Depends(get_db)):
    delivered = case((Shipment.final_status == "delivered", 1), else_=0)
    first_ok = case(
        ((Shipment.final_status == "delivered") & (Shipment.attempts == 1), 1),
        else_=0,
    )
    not_delivered = case((Shipment.final_status != "delivered", 1), else_=0)

    rows = db.execute(
        select(
            Shipment.origin_city,
            Shipment.destination_city,
            func.count(Shipment.id),
            func.sum(delivered),
            func.sum(first_ok),
            func.sum(not_delivered),
        )
        .group_by(Shipment.origin_city, Shipment.destination_city)
    ).all()

    flows = []
    local = []
    for origin, dest, total, n_delivered, n_first_ok, n_not_delivered in rows:
        item = {
            "origin_city": origin,
            "destination_city": dest,
            "shipments": total,
            "delivered": int(n_delivered or 0),
            "first_attempt_success": int(n_first_ok or 0),
            "not_delivered": int(n_not_delivered or 0),
            "first_attempt_success_rate": round((n_first_ok or 0) / total, 4),
        }
        if origin == dest:
            local.append(item)
        else:
            flows.append(item)

    flows.sort(key=lambda r: r["shipments"], reverse=True)
    local.sort(key=lambda r: r["origin_city"])

    return {
        "flows": flows,
        "same_city": local,
        "total_shipments": sum(r["shipments"] for r in flows + local),
        "city_centers": CITY_CENTERS,
    }