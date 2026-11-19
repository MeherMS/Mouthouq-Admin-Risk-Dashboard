"""
Writes PLACEHOLDER random risk scores for every customer and store.

These are NOT model output. They exist only so the API and dashboard can be
built and tested before the batch scoring job exists. They carry no
information about real risk, and they are independent of the synthetic
ground-truth labels.

Usage (from project root):
    python -m scripts.seed_placeholder_scores           # add placeholder rows
    python -m scripts.seed_placeholder_scores --reset   # replace earlier placeholder rows
"""
import argparse
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.models import Customer, EntityType, RiskScore, Store

PLACEHOLDER_VERSION = "placeholder-random-v0"
SEED = 42
BATCH_SIZE = 2000


def band(score: float) -> str:
    """Roadmap section 6: Low 0-39, Medium 40-69, High 70-100."""
    if score < 40:
        return "low"
    if score < 70:
        return "medium"
    return "high"


def random_scores(rng: np.random.Generator, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Skewed toward low scores, as real portfolios usually are. Not calibrated."""
    fraud = np.round(rng.beta(2, 8, n) * 100, 1)
    default = np.round(rng.beta(2, 5, n) * 100, 1)
    return fraud, default


def seed(reset: bool) -> None:
    rng = np.random.default_rng(SEED)
    computed_at = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        if reset:
            result = db.execute(
                delete(RiskScore).where(RiskScore.model_version == PLACEHOLDER_VERSION)
            )
            db.commit()
            print(f"Removed {result.rowcount} earlier placeholder rows")

        for entity_type, model in [
            (EntityType.CUSTOMER, Customer),
            (EntityType.STORE, Store),
        ]:
            entity_ids = list(db.scalars(select(model.id).order_by(model.id)))
            fraud, default = random_scores(rng, len(entity_ids))

            batch: list[RiskScore] = []
            for entity_id, f_score, d_score in zip(entity_ids, fraud, default):
                batch.append(RiskScore(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    fraud_score=float(f_score),
                    default_score=float(d_score),
                    fraud_band=band(float(f_score)),
                    default_band=band(float(d_score)),
                    model_version=PLACEHOLDER_VERSION,
                    computed_at=computed_at,
                    top_factors=None,
                ))
                if len(batch) >= BATCH_SIZE:
                    db.add_all(batch)
                    db.commit()
                    batch = []
            if batch:
                db.add_all(batch)
                db.commit()

            print(f"Wrote {len(entity_ids)} placeholder scores for {entity_type.value}s")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed placeholder risk scores.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete earlier placeholder rows before writing new ones.",
    )
    args = parser.parse_args()
    seed(reset=args.reset)