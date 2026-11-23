# Phase 1: Synthetic Data Foundation

**Project:** Admin Risk Dashboard (Saudi payment platform, prototype)
**Status:** Complete on the small run (1,000 customers, 50 stores, seed 42). The full run (10,000 customers, 500 stores) has not been generated or validated yet.
**Reference:** `technical_roadmap.md`, sections 4 and 5

---

## 1. Purpose

Phase 1 builds the database schema and a synthetic data generator. The generator creates customers, stores, deals, transactions, and payment events with two known risk patterns, default and fraud, plus labels for each. Phase 2 trains models on this data.

The main requirement is that the two risk types are distinguishable on the features in section 6 of the roadmap. If the generator produces data where neither risk is visible, the models will learn nothing useful.

---

## 2. What was built

| Component | File | Purpose |
|---|---|---|
| Dependencies | `requirements.txt` | SQLAlchemy, Alembic, Faker, NumPy, pandas, matplotlib, scikit-learn |
| Config | `app/config.py` | Database URL (SQLite by default, overridable with `DATABASE_URL`) |
| DB setup | `app/db.py` | SQLAlchemy engine, session factory, declarative `Base`, SQLite foreign-key pragma |
| Models | `app/models.py` | Nine tables from roadmap section 4, plus three synthetic-only fields |
| Migrations | `alembic/env.py`, `alembic/versions/*_initial_schema.py` | Schema managed by Alembic |
| Generator config | `app/synthetic/config.py` | Seed, population sizes, profile shares, label window |
| Population generator | `app/synthetic/population.py` | Customers and stores with behavior profiles |
| History generator | `app/synthetic/history.py` | Deals, transactions, payment events, labels |
| Population script | `scripts/generate_population.py` | CLI: creates customers and stores |
| History script | `scripts/generate_history.py` | CLI: creates deals and history, prints summary tables |
| Validation notebook | `notebooks/01_validate_synthetic_data.py` | Integrity checks, feature build, separability tests, Phase 1 exit checks |

---

## 3. Database schema

Nine tables, created by the initial Alembic migration.

| Table | Notes |
|---|---|
| `customers` | Includes `national_id_hash` (SHA-256), `synthetic_profile`, `default_label` |
| `stores` | `account_status` defaults to `active` in the generator |
| `deals` | Includes `is_fraud` (synthetic ground truth) |
| `transactions` | `method`, `status`, `failure_reason` |
| `payment_events` | Includes `occurred_at` (needed for trend features) |
| `risk_scores` | Score history. `entity_id` has no foreign key (points to customers or stores) |
| `actions` | Admin actions. `entity_id` has no foreign key |
| `audit_log` | Intended as append-only. Not yet enforced at the database level |
| `users` | Admin and viewer roles. Empty in Phase 1 |

**Fields added beyond roadmap section 4:**

| Field | Reason |
|---|---|
| `payment_events.occurred_at` | Required to measure whether late payments are trending upward |
| `deals.is_fraud` | Fraud ground truth from the generator |
| `customers.default_label` | Default ground truth, computed by the generator |
| `customers.synthetic_profile` | Behavior profile (`healthy`, `default_prone`, `fraud_actor`) for validation |

The three synthetic-only fields must be removed or isolated before any real data is loaded.

**Enums** are stored as strings (`native_enum=False`), using the enum's value, for example `on_time` rather than `ON_TIME`.

---

## 4. Population generator

### 4.1 Customers

| Profile | Share (target) | Count (small run) |
|---|---|---|
| Healthy | 92% | 922 |
| Default-prone | 6.5% | 63 |
| Fraud actor | 1.5% | 15 |

**Account age:**
- New accounts (20 to 119 days old): 15% of healthy and default-prone customers, 40% of fraud actors.
- Established accounts (120 to about 6 years old): the rest.

This mix means some fraud actors have aged accounts, so account age alone doesn't reveal fraud. It is still a strong signal, because fraud actors are more likely to be new.

**Identity:**
- `national_id_hash` is a SHA-256 hash of a generated 10-digit ID. Raw IDs are never stored.
- Phones use the format `05XXXXXXXX`, generated to be unique.
- Names come from Faker with Saudi Arabic and English locales.

**Shared phone numbers (proxy for device reuse):**
- Fraud actors are grouped into clusters of 3 to 8. Each cluster has a shared phone number, and each member uses it with 60% probability. The rest keep their own number.
- Among healthy customers, 5% are paired into households that share a phone number.

Shared phones are a stand-in for the device-reuse signal in roadmap section 1. The schema has no devices table, which was a deliberate decision for the prototype.

### 4.2 Stores

| Profile | Share (target) | Count (small run) | Dispute rate (generator) |
|---|---|---|---|
| Legitimate | 88% | 39 | 2% |
| High-dispute | 8% | 4 | 15% |
| Fraud | 4% | 7 | 5%, and prices inflated by 25% |

Each store has a category (7 options) and a city (6 Saudi cities). Stores are created 90 days to 5 years before the simulation end.

### 4.3 Reproducibility

- Seed: `42`. The population uses `np.random.default_rng(seed)`.
- Faker is seeded with the same value.
- `scripts/generate_history.py` rebuilds the population from the seed and matches rows to the database by unique keys (`national_id_hash`, `commercial_registration_no`). It does not rely on in-memory state from a previous run.

---

## 5. History generator

Simulation window: 365 days ending at `2026-11-15 00:00 UTC`.

### 5.1 Deal volume

| Profile | Deals per year (mean) | Observed (small run) |
|---|---|---|
| Healthy | 18 | 15.3 per customer |
| Default-prone | 20 | 17.4 per customer |
| Fraud actor | 3 to 8 total, in a burst | 5.4 per customer |

Deal count per customer is Poisson-distributed around the mean. Deals are spread uniformly over the customer's active window.

### 5.2 Deal amounts (SAR)

| Profile | Distribution |
|---|---|
| Healthy | Lognormal, median 900, sigma 0.6 |
| Default-prone | Lognormal, median 1,100, sigma 0.7 |
| Fraud actor | Lognormal, median 1,500, sigma 0.7 |

Fraud-store deals are multiplied by 1.25.

### 5.3 Payment behavior

**Healthy customers:** Payments are almost always on time. Each payment has a small base chance of being missed (0.05%).

**Default-prone customers:**
- Financial stress starts at a random point between 15% and 50% of the customer's window, then rises linearly to 1.0 at the simulation end.
- At stress level `s`, each payment has these probabilities:

| Outcome | Probability |
|---|---|
| Missed | 0.2% + 5% × s² |
| Partial | 1% + 10% × s |
| Late | 3% + 25% × s |
| On time | remainder |

- Installment plans (55% of default-prone deals, 15% of healthy) have 3 or 6 payments, 30 days apart. After a missed installment, the next one is missed with 40% probability.

**Card and bank transfers:** Single payment, with an event at deal time plus 0 to 2 days.

### 5.4 Fraud deal outcomes

For fraud actors, 60% of deals follow the fraud pattern. The other 40% look like normal purchases, to avoid a fully separable signal.

Fraud-pattern deals:

| Outcome | Share of fraud-pattern deals | Result |
|---|---|---|
| Declined | 20% | Deal cancelled, one failed transaction |
| Cancelled after payment | 40% | Deal cancelled, refund event 2 days later |
| Disputed after delivery | 40% | Deal disputed, chargeback event 21 days later |

Fraud actors make almost no payments, so they have very few payment events. This is a known limit (see section 9).

### 5.5 Store-side outcomes

For normal deals:

| Outcome | Legitimate | High-dispute | Fraud store |
|---|---|---|---|
| Cancelled after payment | 2% | 2% | 2% |
| Disputed | 2% | 15% | 5% |
| Completed | remainder | remainder | remainder |

Completed deals older than 30 days are marked `delivered`. Newer ones are marked `paid`.

### 5.6 Labels

**`deals.is_fraud`:** Set to `True` for every deal created by a fraud actor, including the 40% that look normal. The label means "belongs to a fraud actor," not "shows fraud behavior."

**`customers.default_label`:** Set to `True` if any missed payment on a **non-fraud** deal falls within **90 days** of that deal's creation.

- Disputes and chargebacks are not counted. A disputed purchase is not evidence of non-payment.
- Fraud actors always have `default_label = False`.
- Deals near the end of the simulation have an incomplete 90-day window, so their labels may miss later defaults. This is a known limit.

---

## 6. Tuning history

The generator was adjusted several times. Each row shows the default-prone label rate after a change.

| Run | Change | Default-prone label rate | Healthy label rate |
|---|---|---|---|
| 1 | Initial parameters | 77.8% | 0.8% |
| 2 | Lower per-payment miss probability and installment clustering (0.6 → 0.4) | 41.3% | 1.5% |
| 3 | Population change: 15% new accounts for non-fraud customers | 19.0% | 1.1% |
| 4 | Stress starts earlier (window fraction 0.15 to 0.5), fraud actors show normal behavior 40% of the time | 38.1% | 1.0% |

Other fixes along the way:
- **Fraud actors had no deals** because some accounts were created less than 19 days before the simulation end. Fixed by moving the first deal closer to account creation and setting a minimum account age.
- **Fraud separation was perfect** on amounts, cancellations, and account age. Fixed by widening amount overlap, mixing new and aged fraud accounts, and having some fraud deals look normal.

Changes 3 and 4 both moved the default-prone rate. Change 3 came from the population change and was not intended to affect the default rate, so the sensitivity to population shape is worth remembering.

---

## 7. Validation notebook

`notebooks/01_validate_synthetic_data.py` runs in order and covers:

1. **Load:** Reads all tables and normalizes timestamps to naive UTC.
2. **Integrity:** No nulls in required fields, valid foreign keys, no deals or events after the simulation end.
3. **Customer features:** 15 features built only from behavior, never from `default_label`:
   - Account: `account_age_days`, `shared_phone_count`
   - Activity: `n_deals`, `deals_7d`, `deals_30d`, `deals_90d`
   - Outcomes: `cancel_rate`, `dispute_rate`
   - Amounts: `mean_amount`, `max_amount`, `amount_ratio_recent`
   - Payments: `trouble_share`, `missed_share`, `late_share`, `trouble_trend`
4. **Profile medians:** Compares feature medians across profiles.
5. **Separability:** Single-feature AUC for each profile pair. 0.5 means no separation, 1.0 means perfect separation.
6. **Store check:** Dispute rate and price index by store profile.
7. **Phase 1 exit checks:** Pass/fail summary.
8. **Artifact check:** Warns when any single feature has AUC of 0.98 or higher.

### 7.1 Final results (small run)

| Check | Result | Status |
|---|---|---|
| No nulls in required fields | Pass | PASS |
| Foreign keys valid | Pass | PASS |
| No events after simulation end | Pass | PASS |
| Default-prone label rate, 30 to 45% | 38.1% | PASS |
| Healthy label rate, under 2% | 1.0% | PASS |
| Fraud deals, at least 50 | 81 | PASS |
| Default-prone vs healthy, best AUC at least 0.75 | 0.940 | PASS |
| Fraud vs healthy, best AUC at least 0.75 | 0.978 | PASS |
| Fraud vs default-prone, best AUC at least 0.75 | 0.984 | PASS |
| High-dispute stores above legitimate stores | Yes | PASS |

**Remaining warning:** `trouble_share` and `late_share` separate fraud actors from default-prone customers with AUC 0.984 (shown as 0.016 because the direction is inverted). Fraud actors have almost no payment events, so their trouble shares are zero. This is accepted as a known limit (see section 9).

### 7.2 Final dataset size (small run)

| Table | Rows |
|---|---|
| customers | 1,000 |
| stores | 50 |
| deals | 15,312 |
| transactions | 22,248 |
| payment_events | 22,679 |

Fraud deals: 81 across 15 customers.

---

## 8. How to reproduce

From the project root, with the virtual environment active:

```bash
pip install -r requirements.txt
alembic upgrade head
python -m scripts.generate_population --reset
python -m scripts.generate_history
python notebooks/01_validate_synthetic_data.py
```

Expected output: the summary tables from `generate_history`, then the notebook checks. The results in section 7 should match exactly, because the seed is fixed.

For the full-size run:

```bash
python -m scripts.generate_population --full --reset
python -m scripts.generate_history --full
```

The notebook currently uses the small config (`SMALL`). Change it to `FULL` before validating the full run.

---

## 9. Known limits

1. **Labels come from the generator's rules.** Models trained on this data will learn those rules. Validate against real outcomes before production.
2. **Fraud actors have almost no payment history.** Payment-based features separate them from default-prone customers too well. A model may learn "no payment history means fraud," which won't hold on real data.
3. **Account age and cancel/dispute rates are designed signals.** Their separation reflects the generator, not real-world base rates.
4. **Shared phone numbers stand in for device reuse.** There is no device data.
5. **Trouble features leak the default label.** They are computed from the same payment events that create the label. Phase 2 must use a time cutoff.
6. **Incomplete label windows.** Deals in the last 90 days have partial outcome windows, so some default labels may be missing.
7. **Small sample for fraud.** 15 fraud actors and 81 fraud deals are enough to test the pipeline, not to judge model quality. Use the full run before evaluating models.
8. **Synthetic-only fields.** `synthetic_profile`, `default_label`, and `is_fraud` must be removed or isolated before real data is used.
9. **Audit log is not enforced as append-only.** This needs a database-level control before production.
10. **No real-world calibration.** Default and fraud rates, amounts, and timing are chosen by hand, not fitted to data.

---

## 10. Open items

- [ ] Run and validate the full-size dataset (10,000 customers, 500 stores).
- [ ] Confirm that the notebook's fraud separation warnings are acceptable for Phase 2.
- [ ] Add data tests (roadmap section 10) as pytest files: distributions, label rates, no nulls.
- [ ] Decide whether `audit_log` append-only will be enforced now or deferred.

---

## 11. Next: Phase 2

Phase 2 is the ML pipeline. Key requirements, from this phase's findings:

- **Time-based cutoff:** Features use only data before a prediction date. The default label uses only data after it, within the 90-day window. This removes the leakage described in section 9, item 5.
- **Time-based train/test split:** No random splits.
- **Baselines first:** Rule-based fraud score and logistic regression for default. Record metrics before trying gradient boosting.
- **Report fraud-actor payment history separately:** Measure model performance with and without payment features, to check whether the model depends on the known generator artifact in section 9, item 2.