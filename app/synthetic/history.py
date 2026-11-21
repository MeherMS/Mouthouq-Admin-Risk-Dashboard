"""Step 4b: deals, transactions, payment events, and labels."""
from datetime import datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
from faker import Faker
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import (
    Customer,
    Deal,
    DealStatus,
    PaymentEvent,
    PaymentEventType,
    PaymentMethod,
    Store,
    Transaction,
    TransactionStatus,
     Shipment,
)
from app.synthetic.config import GeneratorConfig
from app.synthetic.population import build_customers, build_stores
from app.synthetic.shipments import generate_shipments

# ---------- Behavior parameters ----------

CUSTOMER_PARAMS = {
    "healthy": {
        "deals_per_year": 18.0,
        "base_missed": 0.0005,
        "installment_p": 0.15,
        "amount_mu": np.log(900),
        "amount_sigma": 0.6,
    },
    "default_prone": {
        "deals_per_year": 20.0,
        "base_missed": 0.002,
        "installment_p": 0.55,
        "amount_mu": np.log(1100),
        "amount_sigma": 0.7,
    },
    # Fraud actors are generated separately (burst of deals, see _simulate_customer).
    "fraud_actor": {
        "deals_per_year": 0.0,
        "base_missed": 0.0,
        "installment_p": 0.10,
        "amount_mu": 0.0,
        "amount_sigma": 0.0,
    },
}

# Probability that a completed deal ends in dispute, by store profile.
STORE_DISPUTE_RATE = {"legitimate": 0.02, "high_dispute": 0.15, "fraud_store": 0.05}
CANCEL_RATE = 0.02
FRAUD_STORE_PRICE_INFLATION = 1.25
FRAUD_ACTOR_FRAUD_STORE_SHARE = 0.7

EVENT_TYPES = [
    PaymentEventType.ON_TIME,
    PaymentEventType.LATE,
    PaymentEventType.PARTIAL,
    PaymentEventType.MISSED,
]


# ---------- Rebuilding the population from the seed ----------

def rebuild_population(cfg: GeneratorConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Recreate the Step 4a DataFrames without touching the database.

    Uses the same seed and the same call order as generate_population,
    so the output matches what was inserted.
    """
    rng = np.random.default_rng(cfg.seed)
    fake = Faker(["ar_SA", "en_US"])
    fake.seed_instance(cfg.seed)
    customers = build_customers(rng, fake, cfg)
    stores = build_stores(rng, fake, cfg)
    return customers, stores


def load_db_ids(
    session: Session, customers: pd.DataFrame, stores: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match rebuilt rows to database rows by their unique keys and attach db ids."""
    cust_rows = [tuple(r) for r in session.execute(
        select(Customer.id, Customer.national_id_hash, Customer.created_at)
    ).all()]
    db_c = pd.DataFrame(cust_rows, columns=["db_id", "national_id_hash", "db_created_at"])
    customers = customers.merge(db_c, on="national_id_hash", how="inner")

    store_rows = [tuple(r) for r in session.execute(
        select(Store.id, Store.commercial_registration_no)
    ).all()]
    db_s = pd.DataFrame(store_rows, columns=["db_id", "commercial_registration_no"])
    stores = stores.merge(db_s, on="commercial_registration_no", how="inner")

    if len(customers) != len(cust_rows) or len(stores) != len(store_rows):
        raise RuntimeError(
            "Database population does not match the requested config. "
            "Run generate_population with the same size (--full or not) first."
        )
    return customers, stores


# ---------- Small helpers ----------

def to_naive(value) -> datetime:
    """Convert to a naive UTC datetime. SQLite stores datetimes without timezones."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None)
    return ts.to_pydatetime()


def stress_at(t: datetime, onset: datetime | None, end: datetime) -> float:
    """0 = no financial stress, 1 = full stress. Rises linearly from onset to end."""
    if onset is None or t <= onset:
        return 0.0
    span = (end - onset).total_seconds()
    if span <= 0:
        return 1.0
    return min(1.0, (t - onset).total_seconds() / span)


def sample_event(rng, stress: float, base_missed: float) -> PaymentEventType:
    p_missed = base_missed + 0.05 * stress ** 2
    p_partial = 0.01 + 0.10 * stress
    p_late = 0.03 + 0.25 * stress
    p_on_time = 1.0 - p_missed - p_partial - p_late
    probs = np.array([p_on_time, p_late, p_partial, p_missed])
    return EVENT_TYPES[int(rng.choice(4, p=probs))]


def _card_or_bank(rng) -> PaymentMethod:
    return PaymentMethod.CARD if rng.random() < 0.6 else PaymentMethod.BANK_TRANSFER


def _add_event(txn: Transaction, event_type: PaymentEventType, when: datetime, sim_end: datetime) -> None:
    """Add an event only if it has happened by the end of the simulation."""
    if when <= sim_end:
        txn.payment_events.append(PaymentEvent(event_type=event_type, occurred_at=when))


def _close(deal: Deal, when: datetime, sim_end: datetime) -> None:
    """Record when the deal's outcome became known. Outcomes after the simulation end are not observed."""
    if when <= sim_end:
        deal.closed_at = when


# ---------- Payment builders ----------

def _single_payment(rng, deal, method, t, sim_end, onset, base_missed):
    """One card or bank transaction with one payment event. Returns the missed time or None."""
    txn_time = min(t + timedelta(days=float(rng.uniform(0, 2))), sim_end)
    event_type = sample_event(rng, stress_at(txn_time, onset, sim_end), base_missed)
    missed = event_type == PaymentEventType.MISSED
    txn = Transaction(
        amount_sar=deal.amount_sar,
        method=method,
        status=TransactionStatus.FAILED if missed else TransactionStatus.SUCCEEDED,
        timestamp=txn_time,
        failure_reason="insufficient_funds" if missed else None,
    )
    txn.payment_events.append(PaymentEvent(event_type=event_type, occurred_at=txn_time))
    deal.transactions.append(txn)
    return txn, (txn_time if missed else None)


def _installments(rng, deal, t, sim_end, onset, base_missed) -> list[datetime]:
    """Installment plan: first payment at deal time, then every 30 days. Returns missed times."""
    n = int(rng.choice([3, 6]))
    per_installment = (deal.amount_sar / n).quantize(Decimal("0.01"))
    missed_times: list[datetime] = []
    prev_missed = False

    for i in range(n):
        due = t + timedelta(days=30 * i)
        if due > sim_end:
            break
        if prev_missed and rng.random() < 0.4:
            # Missed payments tend to cluster (a customer who misses one is likely to miss the next).
            event_type = PaymentEventType.MISSED
        else:
            event_type = sample_event(rng, stress_at(due, onset, sim_end), base_missed)

        missed = event_type == PaymentEventType.MISSED
        txn = Transaction(
            amount_sar=per_installment,
            method=PaymentMethod.INSTALLMENT,
            status=TransactionStatus.FAILED if missed else TransactionStatus.SUCCEEDED,
            timestamp=due,
            failure_reason="insufficient_funds" if missed else None,
        )
        txn.payment_events.append(PaymentEvent(event_type=event_type, occurred_at=due))
        deal.transactions.append(txn)

        if missed:
            missed_times.append(due)
        prev_missed = missed

    return missed_times


def _fraud_outcome(rng, deal, t, sim_end) -> None:
    """Fraud deals are declined, cancelled after payment, or disputed after delivery."""
    method = PaymentMethod.CARD if rng.random() < 0.7 else PaymentMethod.BANK_TRANSFER

    if rng.random() < 0.2:
        deal.status = DealStatus.CANCELLED
        deal.transactions.append(Transaction(
            amount_sar=deal.amount_sar,
            method=method,
            status=TransactionStatus.FAILED,
            timestamp=t,
            failure_reason="card_declined",
        ))
        _close(deal, t, sim_end)
    elif rng.random() < 0.5:
        deal.status = DealStatus.CANCELLED
        txn = Transaction(amount_sar=deal.amount_sar, method=method,
                          status=TransactionStatus.SUCCEEDED, timestamp=t)
        deal.transactions.append(txn)
        _add_event(txn, PaymentEventType.REFUND, t + timedelta(days=2), sim_end)
        _close(deal, t + timedelta(days=2), sim_end)
    else:
        deal.status = DealStatus.DISPUTED
        txn = Transaction(amount_sar=deal.amount_sar, method=method,
                          status=TransactionStatus.SUCCEEDED, timestamp=t)
        deal.transactions.append(txn)
        _add_event(txn, PaymentEventType.CHARGEBACK, t + timedelta(days=21), sim_end)
        _close(deal, t + timedelta(days=21), sim_end)


# ---------- Deal and customer simulation ----------

def _simulate_deal(rng, profile, cust_id, store_id, store_profile, t, sim_end, onset):
    """Returns the deal and the times of any missed payments on it."""
    params = CUSTOMER_PARAMS[profile]
    is_fraud = profile == "fraud_actor"

    if is_fraud:
        amount = float(rng.lognormal(np.log(1500), 0.7))
    else:
        amount = float(rng.lognormal(params["amount_mu"], params["amount_sigma"]))
    if store_profile == "fraud_store":
        amount *= FRAUD_STORE_PRICE_INFLATION

    deal = Deal(
        customer_id=cust_id,
        store_id=store_id,
        amount_sar=Decimal(str(round(amount, 2))),
        status=DealStatus.OPENED,
        created_at=t,
        is_fraud=is_fraud,
    )

    if is_fraud and rng.random() < 0.6:
        _fraud_outcome(rng, deal, t, sim_end)
        return deal, []

    base_missed = params["base_missed"]
    r = rng.random()

    # Cancelled before delivery: paid, then refunded.
    if r < CANCEL_RATE:
        deal.status = DealStatus.CANCELLED
        txn = Transaction(amount_sar=deal.amount_sar, method=_card_or_bank(rng),
                          status=TransactionStatus.SUCCEEDED, timestamp=t)
        deal.transactions.append(txn)
        _add_event(txn, PaymentEventType.REFUND, t + timedelta(days=3), sim_end)
        _close(deal, t + timedelta(days=3), sim_end)
        return deal, []

    # Disputed by the store's customer: a single payment, then a chargeback.
    if r < CANCEL_RATE + STORE_DISPUTE_RATE[store_profile]:
        deal.status = DealStatus.DISPUTED
        txn, missed_at = _single_payment(rng, deal, _card_or_bank(rng), t, sim_end, onset, base_missed)
        _add_event(txn, PaymentEventType.CHARGEBACK, t + timedelta(days=30), sim_end)
        _close(deal, t + timedelta(days=30), sim_end)
        return deal, ([missed_at] if missed_at else [])

    # Completed deal.
    if (sim_end - t) > timedelta(days=30):
        deal.status = DealStatus.DELIVERED
        deal.closed_at = t + timedelta(days=7)
    else:
        deal.status = DealStatus.PAID

    if rng.random() < params["installment_p"]:
        return deal, _installments(rng, deal, t, sim_end, onset, base_missed)

    _, missed_at = _single_payment(rng, deal, _card_or_bank(rng), t, sim_end, onset, base_missed)
    return deal, ([missed_at] if missed_at else [])


def _pick_store(rng, is_fraud, store_ids, fraud_store_ids) -> int:
    if is_fraud and fraud_store_ids and rng.random() < FRAUD_ACTOR_FRAUD_STORE_SHARE:
        return int(rng.choice(fraud_store_ids))
    return int(rng.choice(store_ids))


def _simulate_customer(
    rng, cust_id, profile, created, sim_end, hist_limit, cfg,
    store_ids, fraud_store_ids, store_profile_by_id,
) -> tuple[list[Deal], bool]:
    """Returns the customer's deals and their default label."""
    params = CUSTOMER_PARAMS[profile]

    if profile == "fraud_actor":
        # Fraud actors deal in a short burst, which must fall inside the history window.
        if created < hist_limit:
            # Aged account: the burst starts at a random time in the window,
            # leaving 45 days before sim_end so the whole burst fits.
            latest_start = sim_end - timedelta(days=45)
            span_days = (latest_start - hist_limit).total_seconds() / 86400
            start = hist_limit + timedelta(days=float(rng.uniform(0, span_days)))
        else:
            # New account: the burst starts a few days after signup.
            start = created + timedelta(days=int(rng.integers(1, 10)))
        window_days = min(45, (sim_end - start).days)
        n = int(rng.integers(3, 9))
    else:
        start = max(created, hist_limit)
        window_days = (sim_end - start).days
        n = int(rng.poisson(params["deals_per_year"] * window_days / 365))

    if window_days <= 0 or n == 0:
        return [], False

    # Default-prone customers: stress begins somewhere in the middle of their window.
    onset = None
    if profile == "default_prone":
        onset = start + timedelta(days=float(rng.uniform(0.15, 0.5)) * window_days)
    offsets = np.sort(rng.uniform(0, window_days, n))
    deals: list[Deal] = []
    label = False

    for off in offsets:
        t = start + timedelta(days=float(off))
        store_id = _pick_store(rng, profile == "fraud_actor", store_ids, fraud_store_ids)
        deal, missed_times = _simulate_deal(
            rng, profile, cust_id, store_id, store_profile_by_id[store_id], t, sim_end, onset
        )
        deals.append(deal)

        window_end = t + timedelta(days=cfg.default_label_window_days)
        if any(m <= window_end for m in missed_times):
            label = True

    return deals, label


def simulate_history(
    session: Session, cfg: GeneratorConfig, customers: pd.DataFrame, stores: pd.DataFrame
) -> dict[int, bool]:
    """Creates deals, transactions and payment events. Returns {customer_id: default_label}."""
    rng = np.random.default_rng(cfg.seed + 1)  # separate stream from the population
    sim_end = to_naive(cfg.simulation_end)
    hist_limit = sim_end - timedelta(days=cfg.history_days)

    store_ids = [int(i) for i in stores["db_id"]]
    store_profile_by_id = {int(i): p for i, p in zip(stores["db_id"], stores["profile"])}
    fraud_store_ids = [i for i, p in store_profile_by_id.items() if p == "fraud_store"]

    labels: dict[int, bool] = {}
    buffer: list[Deal] = []

    for row in customers.itertuples(index=False):
        cust_id = int(row.db_id)
        deals, label = _simulate_customer(
            rng, cust_id, row.profile, to_naive(row.db_created_at),
            sim_end, hist_limit, cfg, store_ids, fraud_store_ids, store_profile_by_id,
        )
        labels[cust_id] = label
        buffer.extend(deals)

        # Flush in chunks to keep memory use down on the full run.
        if len(buffer) >= 5000:
            session.add_all(buffer)
            session.flush()
            session.expunge_all()
            buffer.clear()

    session.add_all(buffer)
    session.flush()

    session.execute(
        update(Customer),
        [{"id": cid, "default_label": lab} for cid, lab in labels.items()],
    )
    shipment_counts = generate_shipments(session, cfg, store_profile_by_id)
    print("Shipments:", shipment_counts)
    return labels


def reset_history(session: Session) -> None:
    """Delete deals, transactions and payment events. Customers and stores are kept."""
    session.execute(delete(Shipment))
    session.execute(delete(PaymentEvent))
    session.execute(delete(Transaction))
    session.execute(delete(Deal))
    session.execute(update(Customer).values(default_label=None))