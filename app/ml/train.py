"""Default-risk model: train on Feb-May 2026 cutoffs, test on 2026-08-01.

Purge: June and July cutoffs are excluded from training because their 90-day
label windows overlap the test cutoff's label window (Aug 1 to Oct 30).

Run from project root: python -m app.ml.train
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.db import engine
from app.ml.config import HORIZON_DAYS
from app.ml.data import load_tables
from app.ml.features import DEFAULT_FEATURES, build_customer_features
from app.ml.labels import build_labels

TRAIN_CUTOFFS = ["2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01"]
PURGED_CUTOFFS = ["2026-06-01", "2026-07-01"]  # not used, listed for the record
TEST_CUTOFF = "2026-08-01"

PAYMENT_FEATURES = [
    "events_90d", "trouble_share_90d", "missed_share_90d", "late_share_90d", "trouble_trend",
]
NON_PAYMENT_FEATURES = [f for f in DEFAULT_FEATURES if f not in PAYMENT_FEATURES]

REVIEW_FRACTION = 0.01
N_BOOTSTRAP = 1000
RNG_SEED = 42


def build_dataset(tables: dict, cutoffs: list[str]) -> pd.DataFrame:
    frames = []
    for c in cutoffs:
        X = build_customer_features(tables, c)
        labels = build_labels(tables, c)
        y = labels["default_label"].reindex(X.index)
        assert y.notna().all(), f"label/feature index mismatch at {c}"
        frames.append(X.assign(default_label=y.astype(int), cutoff=pd.Timestamp(c)))
    return pd.concat(frames)


def fit(train: pd.DataFrame, features: list[str]):
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    model.fit(train[features], train["default_label"])
    return model


def precision_recall_at_review(y: np.ndarray, p: np.ndarray, fraction: float = REVIEW_FRACTION):
    k = max(1, int(np.ceil(len(y) * fraction)))
    top = np.argsort(-p)[:k]
    hits = int(y[top].sum())
    return hits / k, hits / max(1, int(y.sum()))


def bootstrap_auc_ci(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    rng = np.random.default_rng(RNG_SEED)
    scores = []
    n = len(y)
    while len(scores) < N_BOOTSTRAP:
        idx = rng.integers(0, n, n)
        yb = y[idx]
        if yb.min() == yb.max():  # resample had only one class
            continue
        scores.append(roc_auc_score(yb, p[idx]))
    lo, hi = np.percentile(scores, [2.5, 97.5])
    return float(lo), float(hi)


def calibration_table(y: np.ndarray, p: np.ndarray) -> pd.DataFrame:
    bins = pd.qcut(pd.Series(p), 5, labels=False, duplicates="drop")
    return (
        pd.DataFrame({"bin": bins.to_numpy(), "pred": p, "obs": y})
        .groupby("bin")
        .agg(n=("obs", "size"), mean_pred=("pred", "mean"), observed=("obs", "mean"))
        .round(4)
    )


def evaluate(name: str, y: np.ndarray, p: np.ndarray) -> None:
    base = float(y.mean())
    prec, rec = precision_recall_at_review(y, p)
    lo, hi = bootstrap_auc_ci(y, p)
    constant = np.full_like(p, base)
    print(f"\n== {name} ==")
    print(f"ROC-AUC: {roc_auc_score(y, p):.3f} (95% CI {lo:.3f} to {hi:.3f})")
    print(f"PR-AUC: {average_precision_score(y, p):.3f} (base rate {base:.4f})")
    print(f"Precision / recall at top 1% review: {prec:.3f} / {rec:.3f}")
    print(f"Brier: {brier_score_loss(y, p):.5f} vs constant at base rate {brier_score_loss(y, constant):.5f}")
    print(f"Mean predicted: {p.mean():.4f} vs observed: {base:.4f}")
    print("Calibration by prediction quintile:")
    print(calibration_table(y, p).to_string())


def main() -> None:
    # Guard: every training label window must close before the test cutoff.
    test_start = pd.Timestamp(TEST_CUTOFF)
    for c in TRAIN_CUTOFFS:
        window_end = pd.Timestamp(c) + pd.Timedelta(days=HORIZON_DAYS)
        assert window_end <= test_start, f"training cutoff {c} leaks into test window"

    tables = load_tables(engine)
    train = build_dataset(tables, TRAIN_CUTOFFS)
    test = build_dataset(tables, [TEST_CUTOFF])

    print("Training set by cutoff:")
    print(train.groupby("cutoff")["default_label"].agg(["size", "sum", "mean"]).round(4).to_string())
    print(f"\nTest cutoff {TEST_CUTOFF}: {len(test)} customers, "
          f"{int(test['default_label'].sum())} positives")

    y = test["default_label"].to_numpy()

    model = fit(train, DEFAULT_FEATURES)
    p = model.predict_proba(test[DEFAULT_FEATURES])[:, 1]
    evaluate("Logistic regression, all default features", y, p)

    coef = pd.Series(
        model.named_steps["logisticregression"].coef_[0], index=DEFAULT_FEATURES
    ).sort_values()
    print("\nStandardized coefficients (log-odds per 1 SD):")
    print(coef.round(3).to_string())

    model_np = fit(train, NON_PAYMENT_FEATURES)
    p_np = model_np.predict_proba(test[NON_PAYMENT_FEATURES])[:, 1]
    evaluate("Without payment features", y, p_np)


if __name__ == "__main__":
    main()