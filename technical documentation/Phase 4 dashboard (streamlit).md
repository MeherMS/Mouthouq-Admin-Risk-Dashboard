Phase 4: Admin Dashboard (Streamlit)

Project: Admin Risk Dashboard (Saudi payment platform, prototype)
Status: Complete, except for the SHAP explanation chart, which waits for the batch scoring job. Delivery failures are shown as unavailable.
Reference: technical_roadmap.md, sections 8 and 9

1. Purpose

Phase 4 builds the admin dashboard on top of the Phase 3 API. The dashboard shows each customer and store with two separate risk scores, fraud risk and default risk, and lets an admin act on them. It only calls the API. It never reads the database directly.

All scores in this phase are random placeholders from scripts/seed_placeholder_scores.py. The dashboard shows a warning wherever a placeholder score appears, so no one reads the numbers as model output.

2. What was built
Folder layout

dashboard/
├── config.py               API URL, timeout, band colors
├── api_client.py           HTTP wrapper, error handling
├── common.py               Shared sidebar, badges, formatting,
│                           action and note forms, history,
│                           score history, timeline, band styling
├── app.py                  Overview page (home)
└── pages/
    ├── 1_Customers.py      Customer list, profile, actions
    ├── 2_Action_Log.py     Admin action log, read-only
    └── 3_Stores.py         Store list, profile, actions

app/api/
├── routers/
│   ├── action_log.py       GET /actions
│   ├── dashboard.py        GET /dashboard/summary
│   ├── entity_history.py   GET /customers/{id}/actions, /stores/{id}/actions
│   ├── score_history.py    GET /scores/history/{entity_type}/{id}
│   └── transaction_timeline.py
│                           GET /customers/{id}/transactions, /stores/{id}/transactions
├── schemas.py              StoreStats extended with refund fields
└── routers/stores.py       Refund figures added to store detail

Dependencies

streamlit, requests, pandas, and plotly were added to requirements.txt. The .style.map method used for band colors needs pandas 2.1 or newer.

3. Pages
3.1 Overview (app.py)
Metrics for customers and stores: total, high fraud risk, high default risk.
A grouped bar chart of counts by band, colored green (low), amber (medium), red (high), and gray (unscored). Separate tabs for customers and stores.
A line chart of high-risk score counts per calendar day, from score history. It shows a single point until the scoring job writes several runs.
A table of the top 10 riskiest entities across customers and stores, sorted by the higher of the two scores.
A warning when scores are placeholders.
3.2 Customers (1_Customers.py)
List: search by name, phone, or email. Filters for account status, fraud band, and default band. Sorting by ID, name, created date, or either score. Pagination of 50 rows. The Model column shows the model version. Band cells use the band colors.
Profile, opened by clicking a row:
Fraud and default scores, bands, model version, and computation time.
Top factors as JSON. Empty until the scoring job runs.
Score history chart with dashed lines at Medium (40) and High (70).
Admin actions: Freeze, Unfreeze, Flag for review.
Note form.
Action history: the 50 most recent actions and notes.
Transactions table and a payment event timeline, with the 50 most recent transactions.
Recent deals.
3.3 Stores (3_Stores.py)
List: search by name or registration number. Dropdown filters for category (7 values) and city (6 values), plus account status and bands. Sorting and pagination as for customers.
Profile:
Scores, bands, model version, and score history, as for customers.
Deal statistics: total deals, disputed deals, dispute rate, refunded deals, and refund rate. The refund rate denominator is deals with at least one payment record. The caption states this.
A caption stating that delivery failures are not available.
Admin actions: Approve, Reject, Flag for review.
Note form, action history, transaction timeline, and recent deals.
3.4 Action log (2_Action_Log.py)

A read-only table of every admin action and note, newest first. Filters for entity type, action, admin ID, and entity ID. Pagination of 50 rows.

4. Behavior rules
4.1 Identity

The sidebar offers two identities: Admin (id 1) and Viewer (id 2). The IDs match the output of scripts/seed_users.py. The selected ID is sent in the X-Admin-Id header. Viewers can read everything but cannot change records. Their action buttons and note forms are disabled.

This is a temporary identity. Anyone can switch roles, so the dashboard is safe only on a local machine.

4.2 Confirmation before actions

Every write follows two steps:

Review. The admin enters a reason, at least 3 characters after trimming. Clicking Review shows a confirmation box with the action name and the exact reason. Nothing is sent to the API.
Confirm. Clicking Yes, confirm sends the request. Cancel removes the pending request.

Editing the reason box after Review does not change the pending request. The confirmation shows the text that was reviewed. Only one request can be pending at a time.

4.3 Feedback
changed: true shows a success message.
changed: false (for example, freezing an already frozen account) shows “No change: the record is already in that state.” The API returns this for idempotent actions.
API errors, such as 409 conflicts, show the server’s message.
4.4 Placeholder warnings

Every view that shows a score checks model_version. If it starts with placeholder, the page shows a warning. This covers the Overview, both profiles, and both score history charts.

4.5 Band colors

Band colors come from BAND_COLORS in config.py: green for low, amber for medium, red for high. They are used on profile badges, table cells, and the Overview bar chart. Unscored entities are gray. Trend lines use separate colors for fraud and default, since a line cannot belong to one band.

5. API endpoints added in this phase
Method	Path	Purpose
GET	/dashboard/summary	Band counts, high-risk trend, top 10 riskiest
GET	/actions	Action log with filters and pagination
GET	/customers/{id}/actions	Action history for a customer
GET	/stores/{id}/actions	Action history for a store
GET	/scores/history/{entity_type}/{id}	Score history for chart
GET	/customers/{id}/transactions	Transactions and payment events
GET	/stores/{id}/transactions	Transactions and payment events

Store detail (GET /stores/{id}) gained paid_deals, refunded_deals, and refund_rate.

6. Fixes made during this phase
Trend query on SQLite. Casting a timestamp to Date kept the full timestamp, which SQLAlchemy could not parse. The fix uses func.date(). PostgreSQL will need cast(..., Date) again, so this is marked in the code.
Import names. The refund and timeline code uses Transaction, PaymentEvent, and PaymentEventType. These were confirmed by running the code without errors.
7. Known limits
Placeholder scores. Every score is random. Bands, trends, and the top 10 carry no real risk information until the batch scoring job runs.
SHAP chart missing. Top factors show as JSON. A bar chart waits for the scoring job, which fills top_factors.
Delivery failures not recorded. The schema and generator have no delivery failure field. The store profile marks this as unavailable rather than showing zero.
Temporary identity. The X-Admin-Id header is trusted. Real authentication is still open from Phase 3.
Confirmation is dashboard-only. The API accepts actions without a confirmation step. This matches the roadmap, which places the rule on the admin interface.
Recent records only. Profiles show the 50 most recent actions and transactions. Full history is in the Action log.
Score history is thin. One point per entity until the scoring job writes several dated runs. The trend and score history charts stay flat until then.
Category and city lists are hard-coded. The dropdowns match the current database. A new value needs a code change until the API serves these lists.
Refund rate is an approximation. The denominator is deals with a payment record. It is not a true paid-deal count, because the schema has no paid flag.
Streamlit reruns. Some interactions reload the whole page. Pending confirmations survive navigation until cancelled.
No automated tests for the dashboard. The API has 34 tests from Phase 3. The dashboard was checked by hand.
Audit log not enforced as append-only at the database level.
8. Open items
[ ] Batch scoring job, to replace placeholders and fill top_factors.
[ ] SHAP bar chart on profiles, after the scoring job.
[ ] Score history and trend review, once the job writes several runs.
[ ] Real authentication, replacing X-Admin-Id.
[ ] Database-level append-only enforcement for audit_log.
[ ] Delivery failure data, if the team wants it. This means a schema change, generator changes, and a regenerated dataset, with Phase 2 results rerun.
[ ] Category and city lists served by the API instead of hard-coded.
[ ] Demo script review with the team, and a dashboard test plan.
[ ] Log rejected action attempts (403, 404, 409) to audit_log.
9. Next: Batch scoring job

The scoring job reads the Phase 2 feature pipeline and models, writes one risk_scores row per entity with a real model_version and top_factors, and can be triggered manually. Once it runs, the placeholder warnings disappear and the SHAP chart can be built on the profile pages.