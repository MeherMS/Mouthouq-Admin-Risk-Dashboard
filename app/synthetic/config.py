from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class GeneratorConfig:
    seed: int = 42
    n_customers: int = 1_000
    n_stores: int = 50

    # Fixed reference date so every run produces the same history.
    simulation_end: datetime = datetime(2026, 11, 15, tzinfo=timezone.utc)
    history_days: int = 365

    # Customer profile shares (healthy is the remainder).
    default_prone_share: float = 0.065
    fraud_actor_share: float = 0.015

    # Store profile shares (legitimate is the remainder).
    store_high_dispute_share: float = 0.08
    store_fraud_share: float = 0.04

    # Label rule from the Step 2 decision.
    default_label_window_days: int = 90


SMALL = GeneratorConfig()
FULL = GeneratorConfig(n_customers=10_000, n_stores=500)