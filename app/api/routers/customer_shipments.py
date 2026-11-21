"""Observed shipment history for one customer. Counts and rates from past shipments only.

No predictions. No synthetic ground truth (synthetic_profile, is_fraud) is returned.
Store-marked deliveries are reported separately, because they can be a store-side problem.
"""
from collections import Counter
from statistics import median

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Customer, Deal, Shipment

router = APIRouter(prefix="/customers", tags=["customer shipments"])

LOW_SAMPLE = 10  # ordinary shipments below this count are flagged as unreliable


class ShipmentSummary(BaseModel):
    customer_id: int
    shipments: int
    ordinary_shipments: int
    first_attempt_success_count: int
    first_attempt_success_rate: float | None
    first_attempt_failures: int
    failure_reasons: dict[str, int]
    delivered_on_time_rate: float | None
    median_delivery_days: float | None
    median_promised_days: float | None
    store_claimed_total: int
    store_claimed_returned: int
    low_sample: bool


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


@router.get("/{customer_id}/shipments/summary", response_model=ShipmentSummary)
def customer_shipment_summary(customer_id: int, db: Session = Depends(get_db)):
    if db.get(Customer, customer_id) is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    rows = db.execute(
        select(
            Shipment.final_status,
            Shipment.failure_reason,
            Shipment.store_claimed_delivered,
            Shipment.dispatched_at,
            Shipment.expected_at,
            Shipment.delivered_at,
        )
        .join(Deal, Deal.id == Shipment.deal_id)
        .where(Deal.customer_id == customer_id)
    ).all()

    claimed = [r for r in rows if r.store_claimed_delivered]
    ordinary = [r for r in rows if not r.store_claimed_delivered]
    failed = [r for r in ordinary if r.failure_reason is not None]
    ok_first = len(ordinary) - len(failed)

    delivered = [r for r in ordinary if r.delivered_at is not None]
    on_time = sum(1 for r in delivered if r.delivered_at <= r.expected_at)
    actual_days = [(r.delivered_at - r.dispatched_at).total_seconds() / 86400 for r in delivered]
    promised_days = [(r.expected_at - r.dispatched_at).total_seconds() / 86400 for r in delivered]

    return ShipmentSummary(
        customer_id=customer_id,
        shipments=len(rows),
        ordinary_shipments=len(ordinary),
        first_attempt_success_count=ok_first,
        first_attempt_success_rate=_rate(ok_first, len(ordinary)),
        first_attempt_failures=len(failed),
        failure_reasons=dict(Counter(r.failure_reason for r in failed)),
        delivered_on_time_rate=_rate(on_time, len(delivered)),
        median_delivery_days=round(median(actual_days), 2) if actual_days else None,
        median_promised_days=round(median(promised_days), 2) if promised_days else None,
        store_claimed_total=len(claimed),
        store_claimed_returned=sum(1 for r in claimed if r.final_status == "rto"),
        low_sample=len(ordinary) < LOW_SAMPLE,
    )