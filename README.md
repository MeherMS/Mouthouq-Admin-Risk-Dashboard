# Admin Risk Dashboard

A prototype admin dashboard for a Saudi payment platform. It shows each customer and store with two separate risk scores, **fraud risk** and **default risk**, and lets admins act on them. It also shows observed delivery history for physical-goods orders.

> **Prototype status:** All data is synthetic. Scores are for demonstration only and must not be used for real decisions. Models and rules are early baselines.

---

## Features

- **Two risk scores per customer:** fraud and default, kept separate because they have different causes.
- **Overview dashboard:** risk band counts, trends, and separate top-10 lists for fraud and default.
- **Customer and store profiles:** current scores, score history, contributing factors, transactions, deals, and shipment history.
- **Shipment history:** observed delivery performance per customer, including first-attempt success rate, on-time rate, store-marked returns, and failure reasons.
- **Admin actions:** freeze/unfreeze customers, approve/reject stores, flag for review, and add notes. Every action requires a reason and is written to an audit trail.
- **Action log:** a filterable record of who did what and when.

---

## Architecture

```
Synthetic data generator (customers, stores, deals, payments, shipments)
        │
        ▼
  Scoring pipeline (scripts/run_scoring.py)
  ├─ Default model: logistic regression, percentile ranking
  └─ Fraud model: rule-based
        │
        ▼
  risk_scores table
        │
        ▼
 SQLite database (SQLAlchemy / Alembic)
        │
        ▼
 FastAPI backend  ◄── X-API-Key + X-Admin-Id headers
        │
        ▼
 Streamlit dashboard (calls the API only)
```

- **Database:** SQLite for the prototype, behind SQLAlchemy so moving to PostgreSQL is a configuration change.
- **Backend:** FastAPI. It is the only layer the dashboard talks to. It handles read endpoints, action endpoints, and audit logging.
- **Scoring:** Interpretable baselines. Fraud uses transparent rules. Default uses logistic regression on trailing-window features, with percentile-based bands and per-customer factor explanations.
- **Dashboard:** Streamlit, calling the API only. It never reads the database directly.

---

## Shipment and Delivery Models

The team planned four delivery-related outputs. Each was tested against the synthetic data. The table shows what the prototype currently does for each.

| Output | What the prototype shows | Status |
|---|---|---|
| **Delivery success** | Observed first-attempt success rate for each customer's physical-goods shipments, with the sample size | **Learned model not adopted.** Its scores could not separate customer groups. Shown as history, not as a prediction. |
| **RTO (return to origin)** | A rule-based monitor counting store-marked deliveries that were later returned | **No model.** Only 34 ordinary RTOs exist in the data, too few to learn from. The monitor measures a generator rule, not real behavior. |
| **ETA (expected delivery days)** | A route estimate: the median actual delivery time for each city pair, shown next to the promised date | **Route estimate only.** Its error (0.64 days) is not meaningfully better than the promised date (0.65 days). |
| **Failure reason** | The observed mix of failure reasons for each customer (recipient unavailable, address not found, refused) | **Learned model not adopted.** Accuracy (69.2%) equals always predicting the most common reason. |

**Scope of the shipment data:**
- Shipments exist only for physical-goods stores: electronics, furniture, fashion, and automotive (282 of 500 stores).
- Route distances between the six cities are hand-written approximations, not measured.
- Store-marked deliveries that were returned come from a generator rule, not observed behavior.

---

## Risk Definitions

| Risk | Meaning | Output |
|---|---|---|
| **Default risk** | The customer wants to pay but cannot, due to financial difficulty | Percentile rank among customers. High = top 1% (100 customers), Medium = next 9%, Low = rest. |
| **Fraud risk** | The customer intends to defraud from the start | Rule points (phone shared by another account: 60; two or more cancelled deals in 90 days: 40). Bands: Low 0–39, Medium 40–69, High 70–100. |

Default scores are not calibrated probabilities. Predicted rates are too low, so the dashboard shows percentiles only.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Database | SQLite (PostgreSQL later) |
| ORM and migrations | SQLAlchemy 2.x, Alembic |
| Synthetic data | Faker, NumPy, pandas |
| ML | scikit-learn |
| API | FastAPI, Pydantic |
| Dashboard | Streamlit, Plotly |
| Testing | pytest |
| Hosting (demo) | Render (API), Streamlit Community Cloud (dashboard) |

---

## Project Structure

```
app/            Database models, API, and shared logic
  api/          FastAPI application, routers, schemas, auth
  synthetic/    Synthetic data generator
dashboard/      Streamlit application
scripts/        Data generation, scoring, and user seeding
alembic/        Database migrations
tests/          API and feature tests
notebooks/      Data validation
demo_data/      Seeded demo database (Git LFS)
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- Git LFS (for the demo database)

### Setup

```bash
git clone <repo-url>
cd Mouthouq-Admin-Risk-Dashboard
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Run locally

```bash
# 1. Apply database migrations
alembic upgrade head

# 2. Seed users and compute scores
python -m scripts.seed_users
python scripts/run_scoring.py

# 3. Start the API
uvicorn app.api.main:app --reload

# 4. Start the dashboard (in a second terminal)
streamlit run dashboard/app.py
```

### Configuration

| Variable | Used by | Purpose |
|---|---|---|
| `DATABASE_URL` | API, scripts | Database connection string |
| `API_KEY` | API, dashboard | Shared key required on every request except health checks |
| `API_URL` | Dashboard | Address of the API |

Keep real keys out of the repository. Use environment variables locally and Streamlit secrets in the hosted dashboard.

### Run tests

```bash
python -m pytest tests -v
```

---

## API Overview

| Area | Examples |
|---|---|
| Health | `GET /health`, `GET /health/db` |
| Read | `GET /customers`, `GET /customers/{id}`, `GET /stores`, `GET /stores/{id}` |
| Shipments | `GET /customers/{id}/shipments/summary` |
| Dashboard | `GET /dashboard/summary`, `GET /scores/history/{type}/{id}` |
| Transactions | `GET /customers/{id}/transactions`, `GET /stores/{id}/transactions` |
| Actions (admin) | `POST /customers/{id}/freeze`, `POST /stores/{id}/approve`, `POST /{type}/{id}/flag-review`, `POST /{type}/{id}/notes` |
| Audit | `GET /actions` |

Interactive API docs are disabled by default.

---

## Known Limits

**Data and models**
- **Synthetic data only.** Labels and patterns come from the generator's rules. Results do not describe real customers.
- **Delivery, failure reason, RTO, and ETA are not predictive.** The shipment outputs are observed history or route estimates until real data is available.
- **Fraud actors are rare** (158 customers, 874 deals). Fraud results are fragile.
- **Default model depends on payment-event counts**, largely as a proxy for installment plans, which the generator assigns more often to default-prone customers.
- **Default test results** are not clearly better than the earlier baseline. The difference is within the uncertainty.
- **Shared-phone feature** includes accounts created after the shipment date (a small look-ahead). It is excluded from the default model.
- **Test cutoff reused** across development, so the results confirm the design rather than providing an independent test.
- **Simulation window ends 15 November 2026.** Deals and shipments close to the end are incomplete.

**Platform and security**
- **Placeholder identity.** Admin and viewer roles come from an unverified header. Anyone can switch roles. Do not expose the API beyond trusted users.
- **Shared API key.** One key for the whole team. It cannot identify individual users.
- **Demo hosting is ephemeral.** Admin actions and notes reset when the hosted API restarts.
- **Audit log is not enforced as append-only** at the database level.
- **No automated dashboard tests.** The dashboard was checked by hand.
- **Store scores not built.** Stores currently show as unscored.
- **No compliance review.** PDPL and SAMA requirements must be addressed before any production use.

---

## Roadmap

- Decide the fate of the unused predictions table (drop, or keep empty and documented)
- Regenerate data with a pre-window warm-up and retrain
- Trailing-window trend features for the default model
- Store risk scores
- Real authentication (replacing the header identity and shared key)
- Append-only audit log enforcement
- Measured shipment distances
- Revisit delivery and failure models if richer data becomes available
- Migration to PostgreSQL and a managed host
- Model monitoring, retraining, and feedback from admin decisions

---

## License

Not specified. This is a private project.

## Contact

Meher Selmi: selmi.ms1995@gmail.com