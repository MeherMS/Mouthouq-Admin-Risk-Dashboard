# Admin Risk Dashboard: Phase 1 and Phase 2 Summary

## Purpose

A prototype admin dashboard for a Saudi payment platform. It shows each customer and store with two separate risk scores, fraud risk and default risk, and supports admin actions. This document records what was built, the final results, and the limits we need to state.

## What was built

**Phase 1: Synthetic data foundation**
- A nine-table SQLite schema, managed with Alembic.
- A deterministic generator (seed 42) that produces 10,000 customers, 500 stores, and 365 days of deals, transactions, and payment events, with two designed risk patterns: default-prone customers (gradual financial stress) and fraud actors (short deal bursts, cancellations, disputes, shared phone numbers).
- A validation notebook with integrity checks, separability tests, and exit criteria. All checks pass on the full run.

**Phase 2: ML baselines**
- Cutoff-aware customer features: each feature uses only data from before a cutoff date.
- Forward-looking labels over a 90-day horizon.
- A time-based split: train on February to May 2026, purge June and July, test on August 1, 2026.
- A rule-based fraud score, a logistic regression default model, an XGBoost alternative, a calibration diagnostic, and exact per-customer explanations for the logistic model.
- Unit tests for each module.

## Final results

**Reference dataset:** 152,607 deals, 221,585 transactions, 225,653 payment events, 874 fraud deals. Regenerating from the same seed reproduces these counts exactly.

**Synthetic data validation**
- Default-prone customers: 38.6% default label. Healthy customers: 1.0%.
- Single-feature separability (AUC): default-prone vs healthy 0.92; fraud vs healthy 0.95; fraud vs default-prone 0.93.
- Fraud deals span 13 calendar months. No deals fall before the history window or before customer signup.

**Fraud model (rule-based, frozen)**

| Test cutoff 2026-08-01 | Result |
|---|---|
| ROC-AUC | 0.769 (95% CI 0.656 to 0.871) |
| PR-AUC | 0.036 (95% CI 0.009 to 0.132) |
| Precision / recall at 1% review | 4.6% / 16% |

Two of five rules carry the signal: shared phone numbers and cancellations. The velocity and disputes rules show no lift on training data and are kept as recorded.

**Default model (logistic regression, primary, frozen)**

| Test cutoff 2026-08-01 | Result |
|---|---|
| ROC-AUC | 0.934 (95% CI 0.908 to 0.955) |
| PR-AUC | 0.171 (95% CI 0.125 to 0.239) |
| Precision / recall at 1% review | 23.0% / 20.2% |
| ROC-AUC without payment features | 0.772 |
| Brier score vs constant at base rate | 0.01204 vs 0.01126 |

Removing fraud actors gives essentially the same result (ROC-AUC 0.934), so the default signal is not driven by the fraud population.

**Alternatives and decisions**
- **XGBoost:** ROC-AUC 0.911. Paired difference from logistic regression is -0.027 (95% CI -0.040 to -0.007). Not adopted.
- **Calibration layer:** Fit on training data only. Slope 0.978, intercept -0.14, negligible effect on predictions. Not shipped.
- **Store models:** Deferred.
- **Explanations:** Exact per-customer contributions in log-odds. The additivity check holds to 4e-15.

## Known limits

1. **Generator-defined labels.** The models learn the simulator's rules. Real-world performance is unknown.
2. **Warm-up in training data.** The simulated history starts in November 2025. Payment-derived features reach full coverage only from about mid-July 2026, so every training cutoff falls in the warm-up period and the test cutoff does not.
3. **Cumulative counts drift.** The lifetime payment-event count rises steadily across training cutoffs (mean 4.3 to 10.6). Scores for long-tenured customers would drift upward in production. These features dominate the explanations and should be replaced before any display or production use.
4. **Calibration.** The default model's Brier score is worse than a constant predictor at the test base rate. Individual probabilities should not be read as calibrated risk. The model slightly overpredicts on test.
5. **Shared phones.** The shared-phone coefficient is negative because healthy households share phones in the generator. Real data would not support that pattern.
6. **Test-cutoff reuse.** The August cutoff was evaluated several times across development. Reported results confirm the frozen baseline; they are not an independent test.
7. **Small test set.** 99 default and 25 fraud positives give wide confidence intervals. Small differences between models are noise.
8. **Fraud model is rules, not learned.** Two rules have no lift, and the disputes rule needs a minimum closed-deal count.
9. **No fairness evaluation.** The synthetic data has no protected attributes, so no audit was possible.

## Open items

- Replace cumulative counts with trailing 90-day counts, after checking their stationarity on training data. Not yet validated.
- Regenerate the data with a pre-window warm-up and rerun the baselines (backlog, required before any production model).
- Build the batch scoring job that writes scores, model version, and top factors to `risk_scores`.
- Start Phase 3: the FastAPI backend.

## Status

Phase 1 is complete on the full synthetic dataset. Phase 2 is complete as a prototype baseline: the frozen logistic regression is the default model, with the limits above documented in the model card.