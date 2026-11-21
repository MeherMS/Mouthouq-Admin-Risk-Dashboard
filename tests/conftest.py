import os

# Must be set BEFORE any app module is imported, because app/db.py
# creates the engine from DATABASE_URL at import time.
os.environ["DATABASE_URL"] = "sqlite:///./test_admin_risk.db"
os.environ["API_KEY"] = "test-key"
from datetime import datetime, timezone  # noqa: E402
from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import DATABASE_URL  # noqa: E402

# Safety guard: refuse to run against anything that isn't a test database.
if "test_" not in DATABASE_URL:
    raise RuntimeError(
        f"Refusing to run tests against non-test database: {DATABASE_URL}"
    )

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    AccountStatus,
    Customer,
    Deal,
    DealStatus,
    EntityType,
    RiskScore,
    Store,
    User,
    UserRole,
)


@pytest.fixture
def db_schema():
    """Fresh, empty schema for every test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def seeded(db_schema):
    """
    Known data set:
      customers: c1 (scored, latest default high), c2 (scored, default low),
                 c3 (no score)
      stores:    s1 (scored, 2 deals, 1 disputed), s2 (pending, no score)
      users:     admin (role admin), viewer (role viewer)
    """
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        admin = User(email="admin@test.local", password_hash="x", role=UserRole.ADMIN)
        viewer = User(email="viewer@test.local", password_hash="x", role=UserRole.VIEWER)

        c1 = Customer(name="Alpha", national_id_hash="h1", phone="0500000001",
                      email="alpha@test.local", account_status=AccountStatus.ACTIVE)
        c2 = Customer(name="Beta", national_id_hash="h2", phone="0500000002",
                      email="beta@test.local", account_status=AccountStatus.ACTIVE)
        c3 = Customer(name="Gamma", national_id_hash="h3", phone="0500000003",
                      email="gamma@test.local", account_status=AccountStatus.ACTIVE)

        s1 = Store(name="Shop One", commercial_registration_no="CR1",
                   category="electronics", city="Riyadh",
                   account_status=AccountStatus.ACTIVE)
        s2 = Store(name="Shop Two", commercial_registration_no="CR2",
                   category="fashion", city="Jeddah",
                   account_status=AccountStatus.PENDING)

        db.add_all([admin, viewer, c1, c2, c3, s1, s2])
        db.flush()

        db.add_all([
            Deal(customer_id=c1.id, store_id=s1.id, amount_sar=Decimal("900"),
                 status=DealStatus.PAID, created_at=now),
            Deal(customer_id=c2.id, store_id=s1.id, amount_sar=Decimal("400"),
                 status=DealStatus.DISPUTED, created_at=now),
        ])

        # c1 has two scores. The newer one (85, high) must be the one returned.
        db.add_all([
            RiskScore(entity_type=EntityType.CUSTOMER, entity_id=c1.id,
                      fraud_score=10, default_score=20, fraud_band="low",
                      default_band="low", model_version="test-v1", computed_at=now),
            RiskScore(entity_type=EntityType.CUSTOMER, entity_id=c1.id,
                      fraud_score=12, default_score=85, fraud_band="low",
                      default_band="high", model_version="test-v1", computed_at=now),
            RiskScore(entity_type=EntityType.CUSTOMER, entity_id=c2.id,
                      fraud_score=5, default_score=30, fraud_band="low",
                      default_band="low", model_version="test-v1", computed_at=now),
            RiskScore(entity_type=EntityType.STORE, entity_id=s1.id,
                      fraud_score=20, default_score=15, fraud_band="low",
                      default_band="low", model_version="test-v1", computed_at=now),
        ])
        db.commit()

        return {
            "admin": admin.id,
            "viewer": viewer.id,
            "c1": c1.id,
            "c2": c2.id,
            "c3": c3.id,
            "s1": s1.id,
            "s2": s2.id,
        }
    finally:
        db.close()


@pytest.fixture
def client(seeded):
    from app.api.main import app
    return TestClient(app, headers={"X-API-Key": "test-key"})


@pytest.fixture
def admin_headers(seeded):
    return {"X-Admin-Id": str(seeded["admin"])}


@pytest.fixture
def viewer_headers(seeded):
    return {"X-Admin-Id": str(seeded["viewer"])}


def count_rows(model) -> int:
    """Row count using a fresh session, so the test sees committed data only."""
    db = SessionLocal()
    try:
        return db.query(model).count()
    finally:
        db.close()