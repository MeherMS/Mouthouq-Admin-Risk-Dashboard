import hashlib
from datetime import timedelta

import numpy as np
import pandas as pd
from faker import Faker
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import AccountStatus, Customer, Store
from app.synthetic.config import GeneratorConfig

CATEGORIES = ["electronics", "furniture", "travel", "education",
              "healthcare", "fashion", "automotive"]
CITIES = ["Riyadh", "Jeddah", "Dammam", "Makkah", "Madinah", "Khobar"]
EMAIL_DOMAINS = ["gmail.com", "outlook.com", "hotmail.com", "yahoo.com"]

# Child tables first so foreign keys are respected when resetting.
RESET_ORDER = ["shipment_predictions","shipments","payment_events", "transactions", "deals", "risk_scores",
               "customers", "stores"]

# Offset for the customer city stream. A separate seed means adding city
# does not change any existing draw (names, IDs, phones, profiles, stores).
CITY_SEED_OFFSET = 3


def _unique_ints(rng: np.random.Generator, n: int, low: int, high: int) -> list[int]:
    """Draw n distinct integers in [low, high) without building the full range in memory."""
    seen: set[int] = set()
    out: list[int] = []
    while len(out) < n:
        value = int(rng.integers(low, high))
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _hash_national_id(national_id: str) -> str:
    # Only the hash is stored, following the design note in section 4.
    return hashlib.sha256(national_id.encode()).hexdigest()


def build_customers(rng: np.random.Generator, fake: Faker, cfg: GeneratorConfig) -> pd.DataFrame:
    n = cfg.n_customers
    shares = {
        "healthy": 1 - cfg.default_prone_share - cfg.fraud_actor_share,
        "default_prone": cfg.default_prone_share,
        "fraud_actor": cfg.fraud_actor_share,
    }
    profiles = rng.choice(list(shares), size=n, p=list(shares.values()))

    # New accounts (20-120 days old) appear in every profile, but fraud actors use them more often.
    # Some fraud actors use aged accounts, so account age alone doesn't reveal fraud.
    new_share = np.where(profiles == "fraud_actor", 0.40, 0.15)
    is_new = rng.random(n) < new_share
    days_since_created = np.where(
        is_new,
        rng.integers(20, 120, n),
        rng.integers(120, 6 * 365, n),
    )
    created_at = [cfg.simulation_end - timedelta(days=int(d)) for d in days_since_created]

    national_ids = _unique_ints(rng, n, 10**9, 2 * 10**9)  # Saudi IDs start with 1 or 2
    phones = _unique_ints(rng, n, 0, 10**8)
    domains = rng.choice(EMAIL_DOMAINS, size=n)

    # City uses its own stream so the draws above are unchanged.
    # Uniform over the six cities. Used for shipment origin-destination distance.
    city_rng = np.random.default_rng(cfg.seed + CITY_SEED_OFFSET)
    cities = city_rng.choice(CITIES, size=n)

    df = pd.DataFrame({
        "profile": profiles,
        "cluster_id": None,
        "name": [fake.name() for _ in range(n)],
        "national_id_hash": [_hash_national_id(str(x)) for x in national_ids],
        "phone": [f"05{p:08d}" for p in phones],
        "email": [f"user{i:05d}@{d}" for i, d in enumerate(domains)],
        "city": cities,
        "created_at": created_at,
    })

    # Fraud clusters: members are grouped, but only 60% share a phone.
    # The rest use their own number, which is how real fraud rings avoid simple rules.
    fraud_rows = df.index[df["profile"] == "fraud_actor"].to_list()
    cluster = 0
    pos = 0
    while pos < len(fraud_rows):
        size = int(rng.integers(3, 9))
        members = fraud_rows[pos:pos + size]
        shared_phone = f"05{int(rng.integers(0, 10**8)):08d}"
        df.loc[members, "cluster_id"] = cluster
        for m in members:
            if rng.random() < 0.6:
                df.loc[m, "phone"] = shared_phone
        cluster += 1
        pos += size

    # Family and household pairs among healthy customers also share a phone.
    healthy_rows = df.index[df["profile"] == "healthy"].to_numpy()
    n_pairs = int(0.05 * len(healthy_rows) / 2)
    picks = rng.choice(healthy_rows, size=2 * n_pairs, replace=False)
    for a, b in zip(picks[:n_pairs], picks[n_pairs:]):
        df.loc[b, "phone"] = df.loc[a, "phone"]

    return df

def build_stores(rng: np.random.Generator, fake: Faker, cfg: GeneratorConfig) -> pd.DataFrame:
    n = cfg.n_stores
    shares = {
        "legitimate": 1 - cfg.store_high_dispute_share - cfg.store_fraud_share,
        "high_dispute": cfg.store_high_dispute_share,
        "fraud_store": cfg.store_fraud_share,
    }
    profiles = rng.choice(list(shares), size=n, p=list(shares.values()))
    days_since_created = rng.integers(90, 5 * 365, n)
    registrations = _unique_ints(rng, n, 10**9, 10**10)

    return pd.DataFrame({
        "profile": profiles,
        "name": [fake.company() for _ in range(n)],
        "commercial_registration_no": [str(r) for r in registrations],
        "category": rng.choice(CATEGORIES, size=n),
        "city": rng.choice(CITIES, size=n),
        "created_at": [cfg.simulation_end - timedelta(days=int(d)) for d in days_since_created],
    })


def insert_customers(session: Session, df: pd.DataFrame) -> pd.DataFrame:
    objs = [
        Customer(
            name=row.name,
            national_id_hash=row.national_id_hash,
            phone=row.phone,
            email=row.email,
            city=row.city,
            created_at=row.created_at.to_pydatetime(),
            account_status=AccountStatus.ACTIVE,
            synthetic_profile=row.profile,
            default_label=None,  # set in step 4b
        )
        for row in df.itertuples(index=False)
    ]
    session.add_all(objs)
    session.flush()  # assigns primary keys without committing
    df = df.copy()
    df["db_id"] = [o.id for o in objs]
    return df


def insert_stores(session: Session, df: pd.DataFrame) -> pd.DataFrame:
    objs = [
        Store(
            name=row.name,
            commercial_registration_no=row.commercial_registration_no,
            category=row.category,
            city=row.city,
            created_at=row.created_at.to_pydatetime(),
            account_status=AccountStatus.ACTIVE,
        )
        for row in df.itertuples(index=False)
    ]
    session.add_all(objs)
    session.flush()
    df = df.copy()
    df["db_id"] = [o.id for o in objs]
    return df


def reset_synthetic_data(session: Session) -> None:
    """Delete generated data only. Users, actions, and audit_log are left alone."""
    for table in RESET_ORDER:
        session.execute(text(f"DELETE FROM {table}"))


def generate_population(session: Session, cfg: GeneratorConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(cfg.seed)
    fake = Faker(["ar_SA", "en_US"])
    fake.seed_instance(cfg.seed)

    customers = build_customers(rng, fake, cfg)
    stores = build_stores(rng, fake, cfg)

    customers = insert_customers(session, customers)
    stores = insert_stores(session, stores)
    return customers, stores