from datetime import datetime, timedelta
from decimal import Decimal

from app.db import SessionLocal
from app.models import Deal, DealStatus, Shipment

GROUND_TRUTH_AND_PREDICTION_FIELDS = {
    "synthetic_profile", "is_fraud", "default_label",
    "delivery_success_pct", "expected_days", "reason_if_failed",
}


def _add_shipments(seeded):
    """Three shipments for customer c1, each on its own deal (Shipment.deal_id is unique):
    one delivered on time, one delivered late after a refusal,
    and one store-claimed delivery that came back (RTO)."""
    now = datetime(2026, 9, 1, 12, 0, 0)
    db = SessionLocal()
    try:
        deals = [
            Deal(customer_id=seeded["c1"], store_id=seeded["s1"],
                 amount_sar=Decimal("100"), status=DealStatus.DELIVERED, created_at=now)
            for _ in range(3)
        ]
        db.add_all(deals)
        db.flush()
        d_ok, d_fail, d_claim = deals

        db.add_all([
            Shipment(deal_id=d_ok.id, origin_city="Riyadh", destination_city="Jeddah",
                     dispatched_at=now, expected_at=now + timedelta(days=3),
                     delivered_at=now + timedelta(days=2), attempts=1,
                     final_status="delivered", failure_reason=None,
                     store_claimed_delivered=False),
            Shipment(deal_id=d_fail.id, origin_city="Riyadh", destination_city="Jeddah",
                     dispatched_at=now, expected_at=now + timedelta(days=3),
                     delivered_at=now + timedelta(days=4), attempts=2,
                     final_status="delivered", failure_reason="refused_by_customer",
                     store_claimed_delivered=False),
            Shipment(deal_id=d_claim.id, origin_city="Riyadh", destination_city="Jeddah",
                     dispatched_at=now, expected_at=now + timedelta(days=3),
                     delivered_at=None, attempts=3,
                     final_status="rto", failure_reason="address_not_found",
                     store_claimed_delivered=True),
        ])
        db.commit()
    finally:
        db.close()


def test_counts_separate_claimed_from_ordinary(client, seeded):
    _add_shipments(seeded)
    r = client.get(f"/customers/{seeded['c1']}/shipments/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["shipments"] == 3
    assert body["ordinary_shipments"] == 2
    assert body["first_attempt_failures"] == 1
    assert body["failure_reasons"] == {"refused_by_customer": 1}
    assert body["first_attempt_success_rate"] == 0.5
    assert body["delivered_on_time_rate"] == 0.5
    assert body["store_claimed_total"] == 1
    assert body["store_claimed_returned"] == 1
    assert body["low_sample"] is True


def test_response_has_no_ground_truth_or_predictions(client, seeded):
    _add_shipments(seeded)
    body = client.get(f"/customers/{seeded['c1']}/shipments/summary").json()
    assert not (GROUND_TRUTH_AND_PREDICTION_FIELDS & set(body))


def test_customer_without_shipments(client, seeded):
    body = client.get(f"/customers/{seeded['c2']}/shipments/summary").json()
    assert body["shipments"] == 0
    assert body["first_attempt_success_rate"] is None


def test_unknown_customer_returns_404(client):
    assert client.get("/customers/999999/shipments/summary").status_code == 404