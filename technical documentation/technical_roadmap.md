# Technical Roadmap: Admin Risk Dashboard (Prototype)

## 1. Objective

Build a prototype admin dashboard for the Saudi payment platform. It shows each customer and store with two risk scores, **fraud risk** and **default risk**, and lets admins take actions based on those scores. The prototype runs on synthetic data and is meant to be shared with the whole team.

### Working definitions

| Risk | Meaning | Typical signals |
|---|---|---|
| **Default risk** | Customer wants to pay but lacks funds or is in financial difficulty | Late payments trending upward, shrinking repayment capacity, repeated partial payments, deal size high relative to history, payment plan requests |
| **Fraud risk** | Customer intends to defraud from the start | New or recently changed identity data, mismatched details across records, many deals opened in a short window, deals opened and cancelled, disputes after delivery, device or IP reuse across accounts |

These two risks have different causes and need different features. The model and the synthetic data generator should treat them as separate targets, not one "risk" number.

---

## 2. Recommended Stack

Chosen for speed of building a prototype, with a clear path to larger systems.

| Layer | Prototype choice | Later option |
|---|---|---|
| Database | **SQLite** (single file, zero setup) via SQLAlchemy | PostgreSQL |
| ORM and migrations | SQLAlchemy 2.x + Alembic | Same |
| Synthetic data | Python, Faker, NumPy/pandas | Same |
| ML | scikit-learn (Logistic Regression baseline, Gradient Boosting) and XGBoost; SHAP for explanations | Model registry (MLflow) |
| Backend API | FastAPI | Same |
| Dashboard UI | **Streamlit** (fastest way to share a working prototype with the team) | React + Vite + a charting library |
| Auth | Simple role-based login (admin, viewer) | SSO / managed identity provider |
| Hosting | Local or single container (Docker Compose) | Cloud (GCP or AWS, given the team's existing experience) |

**Why this stack:** Python keeps data, ML, and the API in one language. SQLite needs no server, so the team can run the prototype immediately. SQLAlchemy keeps the move to PostgreSQL a configuration change rather than a rewrite.

---

## 3. System Architecture

```
┌────────────────────┐        ┌──────────────────────┐
│ Synthetic Data     │        │  ML Pipeline          │
│ Generator          │───────▶│  features → train →   │
│ (customers, stores,│        │  score → write scores │
│  transactions, ...)│        └──────────┬───────────┘
└─────────┬──────────┘                   │
          ▼                              ▼
┌─────────────────────────────────────────────────────┐
│ SQL Database (SQLite → PostgreSQL)                  │
│ customers, stores, transactions, deals, risk_scores,│
│ actions, audit_log, users                           │
└──────────────────────────┬──────────────────────────┘
                           ▼
              ┌──────────────────────────┐
              │ FastAPI backend          │
              │ read endpoints, action   │
              │ endpoints, audit logging │
              └────────────┬─────────────┘
                           ▼
              ┌──────────────────────────┐
              │ Admin dashboard          │
              │ (Streamlit prototype)    │
              └──────────────────────────┘
```

---

## 4. Data Model (Initial)

| Table | Key fields |
|---|---|
| `customers` | id, name, national_id_hash, phone, email, created_at, account_status |
| `stores` | id, name, commercial_registration_no, category, city, created_at, account_status |
| `deals` | id, customer_id, store_id, amount_sar, status (opened, paid, delivered, cancelled, disputed), created_at, closed_at |
| `transactions` | id, deal_id, amount_sar, method (card, bank transfer, installment), status, timestamp, failure_reason |
| `payment_events` | id, transaction_id, event_type (on_time, late, missed, partial, chargeback, refund) |
| `risk_scores` | id, entity_type (customer or store), entity_id, fraud_score, default_score, fraud_band, default_band, model_version, computed_at, top_factors (JSON) |
| `actions` | id, entity_type, entity_id, action_type (freeze, unfreeze, approve, reject, flag_review, add_note), reason, admin_id, created_at |
| `audit_log` | id, admin_id, event, payload (JSON), timestamp |
| `users` | id, email, password_hash, role (admin or viewer) |

**Design notes**
- Store the original risk score history, not only the latest value. Admins will ask "is this getting worse?"
- `audit_log` is append-only. Every admin action must be traceable.
- Keep `national_id_hash` hashed even in synthetic data, so the habit is in place before real data arrives.

---

## 5. Synthetic Data Generation

The most important early task. The model can only learn patterns the generator creates, so it must encode both risk types on purpose.

**Population**
- Around 10,000 customers and 500 stores as a starting size, scalable later.
- Around 200,000 deals over 12 months.

**Behavior profiles**
- *Healthy customers* (majority): regular on-time payments, moderate deal sizes.
- *Default-prone customers* (roughly 5–8%): income stress that appears as a gradual rise in late and partial payments, then missed payments. Labels come from later outcomes, not from the start.
- *Fraud actors* (roughly 1–2%): clusters of new accounts, shared devices or contact details, quick high-value deals, cancellations or disputes after delivery, and identity mismatches.
- *Stores*: mostly legitimate; a small share with high dispute rates or delivery failures, and a few showing fraud patterns (fake deliveries, inflated invoices).

**Labels**
- `default_label`: 1 if the customer has a missed or chargeback-level payment outcome within a set window after a deal.
- `fraud_label`: 1 if the deal is marked as fraud by the generator's fraud-actor process.

**Validation of the generator**
- Check that the two risk types are distinguishable: default-prone customers should look different from fraud actors on the features above.
- Keep a fixed random seed so every team member gets the same dataset.

---

## 6. ML Models

Two separate models, one per risk type.

| Model | Target | Baseline | Main model |
|---|---|---|---|
| Default risk | `default_label` | Logistic Regression | Gradient Boosting (XGBoost) |
| Fraud risk | `fraud_label` | Rule-based score (for example, velocity and identity-mismatch rules) | Gradient Boosting, with class weighting (fraud is rare) |

**Features (examples)**
- Account age, number of deals in the last 7 / 30 / 90 days
- Share of late or missed payments, and trend over time
- Deal amount relative to the customer's own history
- Number of cancellations and disputes
- Shared device or contact count across accounts (for fraud)
- Store dispute rate, delivery failure rate, refund rate

**Evaluation**
- Time-based train/test split (never random across time, to avoid leakage).
- Metrics: ROC-AUC and PR-AUC (important because fraud is rare), precision at a fixed review capacity, and calibration.
- Calibrate the output so a "0.7" means roughly a 70% chance, which admins can understand.

**Output**
- A score from 0 to 100 for each risk, mapped to bands: Low (0–39), Medium (40–69), High (70–100). Thresholds are configurable.
- Top 3 contributing factors per score (using SHAP), so admins see *why* an entity is flagged.

**Retraining**
- Batch job that recomputes scores daily (prototype: manual trigger is enough). Each run writes a new `model_version`.

---

## 7. Backend API (FastAPI)

**Read endpoints**
- `GET /customers` and `GET /stores`: list with filters (risk band, status, search)
- `GET /customers/{id}` and `GET /stores/{id}`: profile, current scores, score history, top factors, recent deals
- `GET /dashboard/summary`: counts by risk band, trend of high-risk entities, top flagged entities
- `GET /scores/history/{entity_type}/{id}`: score over time

**Action endpoints** (admin role only, each one writes to `actions` and `audit_log`)
- `POST /customers/{id}/freeze` and `/unfreeze`
- `POST /stores/{id}/approve` and `/reject`
- `POST /{entity_type}/{id}/flag-review`
- `POST /{entity_type}/{id}/notes`

**Cross-cutting**
- Role-based access control on every endpoint.
- Input validation with Pydantic.
- Actions are idempotent where possible (freezing an already frozen account returns success without a duplicate row).
- Errors return clear messages; no stack traces to the client.

---

## 8. Dashboard (Streamlit Prototype)

**Pages**
1. **Overview**: total customers and stores, count by risk band (fraud and default), high-risk trend over time, top 10 riskiest entities.
2. **Customers**: searchable, filterable table; click a row to open a profile.
3. **Stores**: same as customers, with store-specific metrics (dispute rate, delivery failures).
4. **Entity profile**: current scores with bands, score history chart, top factors (SHAP bar chart), deal and transaction timeline, action buttons and notes.
5. **Action log**: who did what and when, filterable.

**Action buttons** show a confirmation with a required reason field before execution.

**Visual conventions**
- Consistent colors for bands: green (low), amber (medium), red (high).
- Show model version and last computed time on every score.

---

## 9. Milestones

### Phase 0: Setup (2–3 days)
- Repo structure, virtual environment, linting, and a `README` with run instructions.
- Docker Compose file so the team can start everything with one command.
- Decide the shared definitions in writing (section 1) and get team sign-off.

### Phase 1: Data foundation (1 week)
- SQLAlchemy models and Alembic migrations for all tables in section 4.
- Synthetic data generator with fixed seed, producing the populations in section 5.
- Validation notebook: charts showing that default-prone and fraud profiles are distinguishable.

### Phase 2: ML models (1–2 weeks)
- Feature pipeline that reads from the database.
- Rule-based fraud baseline and logistic regression default baseline; record metrics.
- Gradient boosting models, time-based evaluation, calibration, and SHAP explanations.
- Batch scoring job that writes to `risk_scores` with `model_version`.

### Phase 3: Backend API (1 week)
- Read endpoints with filters and pagination.
- Action endpoints with RBAC, `actions`, and `audit_log`.
- API tests for the main paths (read, action, permission denied).

### Phase 4: Dashboard (1–2 weeks)
- Overview, customers, stores, entity profile, and action log pages.
- Action flows with confirmation and reason field.
- Seed demo data and a short demo script for the team.

### Phase 5: Team demo and feedback (1 week)
- Demo to the team, collect feedback, and log it as a backlog.
- Document known limits of the synthetic data and models.

**Estimated total:** about 6–8 weeks for one developer working part-time or 3–4 weeks full-time.

---

## 10. Quality, Testing, and Documentation

- **Unit tests** for feature calculations, band mapping, and action rules.
- **Data tests** for the generator: distributions, label rates, no nulls in required fields.
- **Model tests**: metrics above a minimum threshold on the held-out period (guards against silent regressions).
- **Integration tests** for the API against a test SQLite database.
- **Model card** describing data, features, metrics, limitations, and the fact that it uses synthetic data.

---

## 11. Known Limits of the Prototype

- Synthetic data cannot prove model performance on real customers. Real results will differ.
- Default and fraud labels in synthetic data are defined by the generator, so the models learn the generator's rules. Validate with real outcomes before production.
- Single admin-login setup, not enterprise identity.
- No real-time scoring; scores are batch-computed.
- Compliance (PDPL, SAMA requirements) is out of scope for this prototype and must be addressed before production.

---

## 12. Future Path (After the Prototype)

1. **Migrate to PostgreSQL** when data volume or concurrent users grow. Only the connection config and some SQL types should change.
2. **Real-time or near-real-time scoring** for fraud, using a streaming or event-based pipeline.
3. **Replace Streamlit with React** if the dashboard needs more custom UI or public-facing use.
4. **Model operations**: experiment tracking and model registry (MLflow), drift monitoring, and scheduled retraining.
5. **Production security and compliance**: encryption at rest, audit retention, data residency in Saudi Arabia, and a formal review against PDPL and SAMA rules.
6. **Feedback loop**: admin decisions (approve, reject, freeze) become labeled data to improve the models.

---

## 13. Immediate Next Steps

1. Team reviews section 1 (definitions) and section 6 (features). Agree before writing code.
2. Create the repo and Phase 0 setup.
3. Start the synthetic data generator (Phase 1), since everything else depends on it.
