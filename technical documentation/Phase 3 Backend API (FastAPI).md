# Phase 3: Backend API (FastAPI)

**Project:** Admin Risk Dashboard (Saudi payment platform, prototype)
**Status:** Complete. 34 tests passing.
**Reference:** `technical_roadmap.md`, sections 7 and 10

---

## 1. Purpose

Phase 3 builds the FastAPI backend that sits between the database and the admin dashboard. It exposes read endpoints for customers and stores, action endpoints for admin decisions, and an audit trail for every change an admin makes.

The API is the only layer the dashboard talks to. It enforces the rules for what can be read and what can be changed, so the dashboard can stay simple.

---

## 2. What was built

| Component | File | Purpose |
|---|---|---|
| App entry point | `app/api/main.py` | Creates the FastAPI app, registers routers, health checks |
| DB session dependency | `app/api/deps.py` | One database session per request, always closed |
| Response schemas | `app/api/schemas.py` | Pydantic models for every read response, pagination wrapper |
| Query helpers | `app/api/queries.py` | Latest-score subquery, score formatting, NULL-last sorting |
| Customer reads | `app/api/routers/customers.py` | List and detail endpoints |
| Store reads | `app/api/routers/stores.py` | List and detail endpoints, dispute statistics |
| Access control | `app/api/security.py` | Admin role check (temporary header-based identity) |
| Action schemas | `app/api/action_schemas.py` | Reason field validation, action response format |
| Action logic | `app/api/action_service.py` | Status rules, idempotency, writes to `actions` and `audit_log` |
| Action routes | `app/api/routers/actions.py` | Freeze, unfreeze, approve, reject, flag review, notes |
| User seeding | `scripts/seed_users.py` | Creates the prototype admin and viewer accounts |
| Placeholder scores | `scripts/seed_placeholder_scores.py` | Writes random scores so the API can be tested before the scoring job exists |
| Tests | `tests/conftest.py`, `tests/test_read_api.py`, `tests/test_action_api.py` | 33 API tests against a separate test database |

---

## 3. Endpoints

### Read endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check, no database access |
| GET | `/health/db` | Readiness check, confirms database connection |
| GET | `/customers` | List with search (`q`), filters (`account_status`, `fraud_band`, `default_band`), sorting (`sort_by`, `order`), pagination (`limit`, `offset`) |
| GET | `/customers/{id}` | Profile, current scores, 10 most recent deals |
| GET | `/stores` | List with search, filters (`category`, `city`, `account_status`, bands), sorting, pagination |
| GET | `/stores/{id}` | Profile, current scores, dispute statistics, 10 most recent deals |

### Action endpoints (admin role required)

| Method | Path | Effect |
|---|---|---|
| POST | `/customers/{id}/freeze` | Sets status to `frozen` |
| POST | `/customers/{id}/unfreeze` | Sets status to `active`, only from `frozen` |
| POST | `/customers/{id}/flag-review` | Records a review flag, no status change |
| POST | `/customers/{id}/notes` | Records a note, no status change |
| POST | `/stores/{id}/approve` | Sets status to `active` |
| POST | `/stores/{id}/reject` | Sets status to `rejected` |
| POST | `/stores/{id}/flag-review` | Records a review flag, no status change |
| POST | `/stores/{id}/notes` | Records a note, no status change |

Every action requires a `reason` of at least 3 characters after trimming.

---

## 4. Design decisions

### 4.1 Latest score selection

Each entity can have many rows in `risk_scores` (score history). The API always returns the most recent row per entity, selected by the highest `id`. Ids grow with each insert, so this works without relying on timestamps.

### 4.2 Sorting with missing scores

Sorting by score puts unscored entities last in both ascending and descending order. Without this, unscored customers would appear at the top of a "highest risk first" sort.

### 4.3 Ground truth never leaves the database

The following fields are excluded from every response: `synthetic_profile`, `default_label`, `is_fraud`, and `national_id_hash`. The tests check that none of these appear in any read response. This keeps the dashboard from showing the generator's answer key.

### 4.4 Idempotent actions

Actions that would not change anything return success with `changed: false` and write no rows:

- Freezing an already frozen customer
- Unfreezing an already active customer
- Approving an already active store
- Flagging for review twice in a row

Actions that conflict with the current state return 409. For example, unfreezing a customer who is `pending` (not `frozen`).

Notes always create a new row, because each note is a separate record.

### 4.5 Atomic writes

For every action that changes state, the status update, the `actions` row, and the `audit_log` row are written in one transaction. They either all succeed or none do, so the status and the audit trail can't disagree.

### 4.6 Audit payload

Each `audit_log` entry records the entity, the action id, the reason, and the status before and after. This makes each change traceable without querying other tables.

### 4.7 Temporary access control

Admin identity comes from an `X-Admin-Id` header. Anyone can set this header, so it provides no security. It exists so the action endpoints can record who acted and so the role rules (admin can act, viewer cannot) can be tested. It will be replaced by real authentication before any shared or production use.

### 4.8 Error responses

Errors return a short `detail` message. No stack traces are sent to the client.

| Status | Meaning |
|---|---|
| 401 | Missing or unknown admin id |
| 403 | Caller is not an admin |
| 404 | Customer or store not found |
| 409 | Action conflicts with current status |
| 422 | Invalid input (for example, reason too short) |

---

## 5. Placeholder scores

Phase 3 runs before the batch scoring job exists, so `scripts/seed_placeholder_scores.py` writes random scores to `risk_scores`:

- Seed 42, so the output is reproducible.
- Skewed toward low scores, using beta distributions.
- Tagged `model_version = "placeholder-random-v0"`.
- `top_factors` left empty, so the dashboard cannot show fake explanations.

**These scores are not model output and carry no information about real risk.** They are independent of the synthetic ground-truth labels. Any demo must state this clearly.

Result: 10,000 customer scores and 500 store scores written.

---

## 6. Testing

Tests run with pytest against a separate database, `test_admin_risk.db`. A safety guard in `conftest.py` refuses to run if the database URL does not contain `test_`, so development data cannot be wiped by mistake.

Each test starts from a freshly built schema with a small known data set (3 customers, 2 stores, 2 users).

| File | Tests | Covers |
|---|---|---|
| `test_read_api.py` | 15 | List and detail endpoints, search, filters, sorting, pagination, latest score, NULL handling, 404s, ground-truth fields absent |
| `test_action_api.py` | 19 | Access control (401, 403), validation (422), freeze and unfreeze, idempotency, 409 conflicts, flag and note behavior, store actions, audit payload |

**Result:** 34 passed, including the earlier tests already in the project.

Run with:

```bash
python -m pytest tests -v
```

---

## 7. Known limits

1. **No real authentication.** The `X-Admin-Id` header is trusted without verification. The API must not be exposed beyond a local machine until login is added.
2. **Placeholder scores.** Every score is random. Band filters and sorts work correctly, but the values carry no meaning until the scoring job replaces them.
3. **Audit log not enforced as append-only.** The application only inserts into `audit_log`, but the database does not block updates or deletes. This is an open item from Phase 1.
4. **Rejected attempts are not logged.** Requests that return 409, 403, or 404 leave no trace in `audit_log`. A compliance trail may need them.
5. **Flag-review deduplication is shallow.** A repeated flag is ignored only if it directly follows another flag. A flag after a note is recorded again.
6. **Store-side features are limited.** The store detail shows dispute rate only. Delivery failures and refund rate from the roadmap are not yet exposed.
7. **No pagination on deal history.** Customer and store detail show the 10 most recent deals only.
8. **Unseeded data in tests.** The test fixtures use hand-built data, not the generator output. Behavior on the full 152,607-deal dataset has not been load-tested.

---

## 8. Open items

- [ ] Replace `X-Admin-Id` with real authentication (roadmap section 7, auth).
- [ ] Build the batch scoring job to replace placeholder scores and fill `top_factors` (Phase 2 open item).
- [ ] Decide whether to log rejected action attempts to `audit_log`.
- [ ] Enforce `audit_log` as append-only at the database level (Phase 1 open item).
- [ ] Add delivery failure and refund rate to store statistics.
- [ ] Load-test the endpoints on the full dataset.

---

## 9. Next: Phase 4

Phase 4 is the Streamlit dashboard: overview, customers, stores, entity profile, and action log pages. The dashboard will call the API only, never the database directly. Before Phase 4 starts, the batch scoring job is recommended so the dashboard shows real model output rather than placeholders.