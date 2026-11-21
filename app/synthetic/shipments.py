"""Step 4c: shipments for physical-goods deals.

Uses its own random stream (seed + 2), so deals, transactions, payment events
and labels are unchanged. Distances are hand-written approximations (road km),
not measured data. Shipments whose outcome falls after the simulation end are
not recorded, the same rule the deal generator uses for closed_at.
"""
import math
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.models import Customer, Deal, DealStatus, Shipment, Store
from app.synthetic.config import GeneratorConfig

SHIPMENT_SEED_OFFSET = 2
PHYSICAL_CATEGORIES = {"electronics", "furniture", "fashion", "automotive"}
MAX_ATTEMPTS = 3
RETRY_GAP_DAYS = 2
KM_PER_DAY = 400            # rough average road transit speed
INTRA_CITY_KM = 15
FAKE_DELIVERY_RATE = 0.15   # fraud stores: share of shipments the store claims were delivered
CHUNK = 5000

# Approximate road distances in km. Hand-written, labeled approximate, NOT measured.
_ROAD_KM = {
    ("Riyadh", "Jeddah"): 950,
    ("Riyadh", "Makkah"): 870,
    ("Riyadh", "Madinah"): 850,
    ("Riyadh", "Dammam"): 400,
    ("Riyadh", "Khobar"): 410,
    ("Jeddah", "Makkah"): 75,
    ("Jeddah", "Madinah"): 420,
    ("Jeddah", "Dammam"): 1300,
    ("Jeddah", "Khobar"): 1320,
    ("Makkah", "Madinah"): 420,
    ("Makkah", "Dammam"): 1250,
    ("Makkah", "Khobar"): 1270,
    ("Madinah", "Dammam"): 1180,
    ("Madinah", "Khobar"): 1200,
    ("Dammam", "Khobar"): 25,
}

# Per-attempt failure probability and reason mix, by customer profile.
# Reason weights in each profile sum to 1.0.
DELIVERY_PARAMS = {
    "healthy": {
        "p_fail": 0.06,
        "reasons": {"address_not_found": 0.20, "recipient_unavailable": 0.70,
                    "refused_by_customer": 0.10},
    },
    "default_prone": {
        "p_fail": 0.10,
        "reasons": {"address_not_found": 0.20, "recipient_unavailable": 0.50,
                    "refused_by_customer": 0.30},
    },
    "fraud_actor": {
        "p_fail": 0.25,
        "reasons": {"address_not_found": 0.70, "recipient_unavailable": 0.20,
                    "refused_by_customer": 0.10},
    },
}


def _to_naive(value) -> datetime:
    """SQLite returns naive datetimes; strip any timezone defensively."""
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def distance_km(a: str, b: str) -> int:
    if a == b:
        return INTRA_CITY_KM
    key = (a, b) if (a, b) in _ROAD_KM else (b, a)
    return _ROAD_KM[key]  # KeyError if a city pair is missing


def _transit_days(origin: str, dest: str) -> int:
    return max(1, math.ceil(distance_km(origin, dest) / KM_PER_DAY))


def _pick_reason(rng, reasons: dict[str, float]) -> str:
    names = list(reasons)
    probs = np.array([reasons[n] for n in names])
    return names[int(rng.choice(len(names), p=probs))]


def _simulate_shipment(rng, profile, store_profile, origin, dest, dispatched):
    """Returns (row, closed_at). closed_at is used only for the end-of-simulation check."""
    params = DELIVERY_PARAMS[profile]
    transit = _transit_days(origin, dest)
    fake = store_profile == "fraud_store" and rng.random() < FAKE_DELIVERY_RATE

    first_reason = None
    attempts = 0
    delivered = False
    if fake:
        # Store claims delivery; the carrier returns the goods after all attempts.
        attempts = MAX_ATTEMPTS
        first_reason = "address_not_found"
    else:
        for k in range(1, MAX_ATTEMPTS + 1):
            attempts = k
            if rng.random() >= params["p_fail"]:
                delivered = True
                break
            if first_reason is None:
                first_reason = _pick_reason(rng, params["reasons"])

    retry_days = (attempts - 1) * RETRY_GAP_DAYS
    if delivered:
        delay = float(rng.gamma(2.0, 0.5))  # small random delay, mean 1 day
        delivered_at = dispatched + timedelta(days=transit + retry_days + delay)
        final_status = "delivered"
        closed_at = delivered_at
    else:
        delivered_at = None
        final_status = "rto"
        # Outbound transit, retry gaps, then the return trip.
        closed_at = dispatched + timedelta(days=2 * transit + retry_days)

    row = {
        "origin_city": origin,
        "destination_city": dest,
        "dispatched_at": dispatched,
        "expected_at": dispatched + timedelta(days=transit + 1),  # promised ETA, with 1-day buffer
        "delivered_at": delivered_at,
        "attempts": attempts,
        "final_status": final_status,
        "failure_reason": first_reason,
        "store_claimed_delivered": fake,
    }
    return row, closed_at


def _simulate_disputed_fraud(rng, origin, dest, dispatched):
    """Fraud actor, deal disputed after delivery: delivered on first attempt,
    and the store recorded it as delivered."""
    transit = _transit_days(origin, dest)
    delay = float(rng.gamma(2.0, 0.5))
    delivered_at = dispatched + timedelta(days=transit + delay)
    row = {
        "origin_city": origin,
        "destination_city": dest,
        "dispatched_at": dispatched,
        "expected_at": dispatched + timedelta(days=transit + 1),
        "delivered_at": delivered_at,
        "attempts": 1,
        "final_status": "delivered",
        "failure_reason": None,
        "store_claimed_delivered": True,
    }
    return row, delivered_at


def generate_shipments(session: Session, cfg: GeneratorConfig,
                       store_profile_by_id: dict[int, str]) -> dict[str, int]:
    """Creates one shipment per eligible deal. Returns counts for the run."""
    rng = np.random.default_rng(cfg.seed + SHIPMENT_SEED_OFFSET)
    sim_end = _to_naive(cfg.simulation_end)

    stmt = (
        select(
            Deal.id, Deal.status, Deal.created_at, Deal.is_fraud, Deal.store_id,
            Store.city, Store.category,
            Customer.city, Customer.synthetic_profile,
        )
        .select_from(Deal)
        .join(Store, Store.id == Deal.store_id)
        .join(Customer, Customer.id == Deal.customer_id)
        .order_by(Deal.id)
    )

    counts = {"created": 0, "unresolved": 0, "not_eligible": 0}
    batch: list[dict] = []

    for (deal_id, status, created_at, is_fraud, store_id, store_city, category,
         cust_city, profile) in session.execute(stmt).all():
        if category not in PHYSICAL_CATEGORIES:
            counts["not_eligible"] += 1
            continue

        disputed_fraud = bool(is_fraud) and status == DealStatus.DISPUTED
        if not disputed_fraud and status not in (DealStatus.PAID, DealStatus.DELIVERED):
            counts["not_eligible"] += 1
            continue

        dispatched = _to_naive(created_at) + timedelta(days=float(rng.uniform(0, 2)))

        if disputed_fraud:
            row, closed_at = _simulate_disputed_fraud(rng, store_city, cust_city, dispatched)
        else:
            row, closed_at = _simulate_shipment(
                rng, profile, store_profile_by_id[store_id],
                store_city, cust_city, dispatched,
            )

        if closed_at > sim_end:
            counts["unresolved"] += 1
            continue

        row["deal_id"] = deal_id
        batch.append(row)
        counts["created"] += 1

        if len(batch) >= CHUNK:
            session.execute(insert(Shipment), batch)
            batch.clear()

    if batch:
        session.execute(insert(Shipment), batch)
    session.flush()
    return counts