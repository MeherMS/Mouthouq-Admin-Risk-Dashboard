# Phase 5: Team Demo Deployment (Free Tier)

**Project:** Admin Risk Dashboard (Saudi payment platform, prototype)
**Status:** Backend deployed on Render (free). Dashboard deployment on Streamlit Community Cloud in progress. API key not yet added.
**Reference:** `technical_roadmap.md`, sections 9 (Phase 5) and 12

---

## 1. Purpose

This phase puts the prototype in front of the team. It has three parts: a working scoring engine so the dashboard shows model output instead of placeholders, a deployment that a small group can open from a browser, and a wait message that handles the free hosting plan's cold starts.

It is a demo deployment, not a production system. It runs on synthetic data, uses a temporary identity, and is shared only with named people.

---

## 2. What was built

| Component | File or service | Purpose |
|---|---|---|
| Scoring engine (v1) | `scripts/run_scoring.py` | Writes customer scores to `risk_scores` |
| Config for deployment | `dashboard/config.py` | Reads the API address from Streamlit secrets, or from an environment variable, or falls back to localhost |
| Backend status check | `dashboard/backend_status.py` | Waits for the API's `/health` endpoint and shows a message while the free instance wakes up |
| Shared sidebar | `dashboard/common.py` (`render_sidebar`) | Calls the status check on every page |
| Factor chart | `dashboard/pages/1_Customers.py` | Bar chart of default risk drivers, plus a list of fraud rules that fired |
| Timestamp fix | `dashboard/common.py` | Parses `computed_at` with `format="ISO8601"` so scores with and without microseconds both load |
| Source control | Private GitHub repo `Mouthouq-Admin-Risk-Dashboard` | Code, with `.gitignore` and Git LFS for the demo database |
| API hosting | Render, free web service | Runs the FastAPI app |
| Dashboard hosting | Streamlit Community Cloud | Runs the Streamlit app, restricted to named viewers |

---

## 3. Scoring engine (v1)

`scripts/run_scoring.py` is a self-contained implementation of the Phase 2 baseline. It does not import the Phase 2 modules, because those could not be checked against the current code.

**Default risk:** logistic regression on eight features, all calculated from data before the scoring cutoff: account age, deals in 30 and 90 days, cancellations in 90 days, the late, partial, and missed payment shares over 90 days, and the log of mean deal amount over 90 days. Training uses four monthly cutoffs (February to May 2026). The test cutoff is 1 August 2026, with a 90-day label horizon.

**Fraud risk:** rule-based. A customer gets 60 points if a phone number is shared by two or more accounts, and 40 points for two or more cancelled deals in 90 days. Points are capped at 100.

**Bands:** Low (0 to 39), Medium (40 to 69), High (70 to 100), using the absolute probability scale.

**Output:** 10,000 customer scores, written with `model_version = lr-default-v1+rules-fraud-v1`.

### 3.1 Results

| Measure | Value |
|---|---|
| Default test ROC-AUC | 0.721 |
| Default test base rate | 2.4% |
| Default bands | 9,999 low, 1 medium |
| Fraud bands | 9,379 low, 601 medium, 20 high |

### 3.2 Decision

The Phase 2 reference result was ROC-AUC 0.934. The v1 engine is lower because it leaves out the trend features (`trouble_trend`, `amount_ratio_recent`) that the Phase 1 notebook used. The team decided to keep v1 for the demo and treat the trend-feature version as an optional later step. The gap should be stated plainly in the demo.

---

## 4. Deployment

### 4.1 Source control

The repo is private and contains no database, virtual environment, or cache files. The `.gitignore` excludes `*.db`, with one exception: `demo_data/risk.db`. That file is tracked with Git LFS, so the seeded database ships with the code.

### 4.2 API on Render (free)

| Setting | Value |
|---|---|
| Runtime | Python 3 |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.api.main:app --host 0.0.0.0 --port $PORT` |
| Environment | `DATABASE_URL = sqlite:///./demo_data/risk.db`, `PYTHON_VERSION` set to the local version |
| Health check path | `/health` |

The free plan has no persistent disk and no paid Shell, so the database is committed to the repo instead of seeded on the server. Actions written during a session (freeze, approve, notes) are lost when the instance restarts. Scores, customers, and history stay fixed.

### 4.3 Dashboard on Streamlit Community Cloud

| Setting | Value |
|---|---|
| Repo and branch | `Mouthouq-Admin-Risk-Dashboard`, `main` |
| Main file | `dashboard/app.py` |
| Secrets | `API_URL` set to the Render service URL, with no trailing slash |
| Sharing | Only specific people (team email addresses) |

### 4.4 Deployment issues found and fixed

| Issue | Cause | Fix |
|---|---|---|
| Score history crashed with a `ValueError` on timestamps | `pd.to_datetime` inferred a format from the first row, which had microseconds. Rows from `run_scoring` have none | Pass `format="ISO8601"` and `errors="coerce"` |
| Dashboard failed to start on Streamlit Cloud (`ImportError`) | `config.py` defined `API_URL`, but `api_client.py` imported `API_BASE_URL` | Added `API_BASE_URL = API_URL` as an alias |
| `findstr` failed on a regex-style search from PowerShell | `findstr` splits arguments at spaces | Used a short Python script for searches |

---

## 5. Free-tier behavior

Render's free instance sleeps after a period with no traffic. The first request after a sleep can take about a minute, and the front end used to fail during that time.

`dashboard/backend_status.py` polls the API's `/health` endpoint every three seconds for up to 90 seconds. While it waits, it shows a message that the free hosting plan may take up to a minute to wake up. Once the API answers, the page loads, and the ready flag is stored in the Streamlit session so later page changes skip the check. If the API does not answer within 90 seconds, the page shows an error and stops.

The check is called from `render_sidebar()`, which every page uses.

**Known limit:** the ready flag lasts for the whole browser session. If Render sleeps during a long session, requests can fail, and the page shows the API error. Reloading the tab fixes it.

---

## 6. Known limits

1. **The API is public.** Anyone who finds the Render URL can call it and send `X-Admin-Id: 1` to act as admin. The Streamlit sharing list protects the dashboard, not the API. This is the most important open item.
2. **Temporary identity.** The `X-Admin-Id` header is trusted, and the dashboard lets the user choose Admin or Viewer.
3. **Actions are not persistent.** Admin actions and notes reset on every Render restart.
4. **Database is a snapshot.** Scores and data reflect the seed at commit time. Changing the data means regenerating locally, committing the new file, and redeploying.
5. **Default bands are almost all low.** 9,999 of 10,000 customers are in the low default band, because probabilities rarely reach 40 at a 2.4% base rate. Admins cannot use the default band to find customers yet.
6. **Default model is weaker than Phase 2.** Test ROC-AUC is 0.721 against 0.934 for the Phase 2 reference.
7. **Fraud model is two rules.** It flags shared phones and repeated cancellations. The Phase 2 velocity and dispute rules are not included.
8. **Synthetic data only.** Labels and patterns come from the generator. Results do not describe real customers.
9. **Cold starts.** The first load after idle time is slow, and a session can still hit a timeout mid-use.
10. **No automated tests for the dashboard.** The API has its own tests; the dashboard was checked by hand.
11. **Audit log is not append-only at the database level.** Still open from Phase 1.

---

## 7. Open items

- [ ] Confirm the Streamlit deployment loads all pages, and record the result.
- [ ] Add a shared API key: the API checks a required header on every request, and the dashboard sends it from Streamlit secrets. This needs `app/api/main.py`.
- [ ] Disable or restrict `/docs` before wider sharing.
- [ ] Decide whether the default band should use review capacity (top 1% flagged) instead of absolute probability.
- [ ] Trend-feature version of the default model, with a before-and-after AUC.
- [ ] Demo script for the team, stating that scores come from the synthetic-data scorer.
- [ ] Real authentication, replacing `X-Admin-Id`.
- [ ] Database-level append-only enforcement for `audit_log`.

---

## 8. Next steps

1. Confirm the dashboard loads on Streamlit Cloud and that the wait message appears after an idle period.
2. Add the API key, then restrict access to the API docs.
3. Run the team demo using the demo script, and log feedback as the Phase 5 backlog.
4. Plan the move to a paid host and PostgreSQL only if the team decides to continue beyond the prototype (roadmap section 12).
```"