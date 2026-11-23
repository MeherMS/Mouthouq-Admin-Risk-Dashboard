# Admin Risk Dashboard: Phase Summary

**Project:** Admin Risk Dashboard (Saudi payment platform, prototype)
**Period covered:** Phase 1 data extension, Phase 2 model rewrite, shipment extension, dashboard and API updates, and deployment preparation
**Status:** Local build complete. Repository push and hosting setup in progress. All data is synthetic.

---

## 1. Purpose of this phase

This phase had three goals:

1. Replace the default-risk model with one that uses only data known at the time of prediction, and ensure the live scores come from the same code that was tested.
2. Extend the synthetic data with physical shipments, so the team could evaluate delivery-related models.
3. Prepare the prototype for a shared team demo, with access control, a corrected dashboard, and documentation.

The phase also included a set of model attempts that did not succeed. Those results are recorded here so the team can see what was tested and why it was not adopted.

---

## 2. What changed, at a glance

| Area | Change | Status |
|---|---|---|
| Customer data | Added a `city` field to customers | Done |
| Shipment data | Added a shipments table and generator for physical-goods stores | Done |
| Default risk model | Rewritten with trailing-window features and a shared feature module | Done |
| Scoring engine | Replaced with v2: percentile default scores, unchanged fraud rules | Done |
| Dashboard | Percentile labels, corrected thresholds, separate fraud and default top lists, plain-language factor names, shipment panel | Done |
| API | Customer shipment summary endpoint; shared API key; interactive docs off by default | Done |
| Delivery and failure-reason models | Trained and evaluated; not adopted | Closed (negative result) |
| RTO model | Not built; rule-based monitor only | Closed |
| ETA | Route-based estimate only | Done |
| Store risk scores | Deferred; stores show as Unscored | Deferred |
| Repository and hosting | Push and deployment | In progress |

---

## 3. Data generator changes

### 3.1 Customer population (unchanged counts)

The population was regenerated with the fixed seed (42). The counts match the reference run.

| Profile | Customers |
|---|---|
| Healthy | 9,215 |
| Default-prone | 627 |
| Fraud actor | 158 |
| **Total** | **10,000** |

Fraud actors form 27 clusters that share phone numbers. Store population: 444 legitimate, 36 high-dispute, 20 fraud stores (500 total).

### 3.2 Customer city

Each customer received a city from the six Saudi cities used for stores. The city values come from a separate random seed, so no existing population draw changed. Distribution is roughly even, between 1,600 and 1,731 customers per city.

### 3.3 Deal history (unchanged)

The history generator was not changed. The reference counts were rechecked after every data change and matched each time:

| Table | Rows |
|---|---|
| Deals | 152,607 |
| Transactions | 221,585 |
| Payment events | 225,653 |
| Fraud deals | 874 |

Default labels remain: 38.6% for default-prone customers and 1.0% for healthy customers.

### 3.4 Shipments (new)

**Eligible stores.** Shipments are created only for physical-goods categories: electronics, furniture, fashion, and automotive (282 of 500 stores). Travel, education, and healthcare are treated as services and have no shipments. The category list was checked against the database; all seven values matched.

**Eligible deals.** Shipments are created for deals that are paid or delivered at physical stores, and for fraud-actor disputes after delivery.

**Result.** 80,380 shipments:

| Final status | Count |
|---|---|
| Delivered | 79,914 |
| Returned to origin (RTO) | 466 |

**Store-side rule.** Fraud stores mark some shipments as delivered when they were not (553 claimed shipments). Of these, 432 are returned. This is a generator rule, not observed behavior.

**Failure reasons (first attempt, ordinary shipments only):**

| Reason | Count |
|---|---|
| Recipient unavailable | 3,353 |
| Address not found | 1,483 |
| Refused by customer | 591 |

**Distances.** Route distances between the six cities are hand-written approximations, labeled as such. They were not measured.

**Random seed.** Shipments use their own seed, so no existing deal, payment, or label changed.

---

## 4. Shipment data validation

Before any model was trained, a read-only check tested whether the shipment targets separate customer groups.

| Check | Result | Verdict |
|---|---|---|
| First-attempt failure, fraud actors vs healthy | 2.14 times the healthy rate (fraud actor sample: 266 shipments) | Pass, with a wide interval |
| Ordinary RTO count | 34 (432 of 466 RTOs come from the store-side rule) | Fail. Too few for a learned model |
| Failure reason by profile | Address-not-found share 79% for fraud actors, 21% for healthy | Pass, on a small sample (34 fraud failures) |
| ETA: city-pair estimate vs promised date | 0.63 vs 0.64 days mean absolute error | Fail. No meaningful gain over the promised date |

**Overall:** Delivery failure and failure reason separate the groups in the generator. RTO and ETA do not support learned models on this data. The generator separates groups; this does not show that the models would work on real shipments.

---

## 5. Default risk model (rewritten)

### 5.1 Why it was rewritten

The Phase 2 model used cumulative counts (for example, total deals and total payment events since signup). These counts grow over time, so a model trained on early snapshots and tested on later ones was extrapolating. The Phase 2 live scorer also used a simplified feature set, so the scores on the dashboard did not come from the validated model. The reported 0.934 result and the live score quality (0.721) differed.

### 5.2 What changed

- **Features** use only trailing windows: 30 and 90 days for deals, outcomes, amounts, and payment events. Cumulative counts were removed.
- **One feature module** is used for training, evaluation, and scoring. The live scorer imports the same code as the test.
- **Labels** follow the Phase 2 definition: a missed payment on a non-fraud deal within 90 days after the cutoff.
- **Shared phone count** is computed for analysis only and is excluded from the default model, because of a generator artifact (household phone sharing shows a negative effect).

### 5.3 Training and test design

- Training cutoffs: 1 February, 1 March, 1 April, and 1 May 2026 (7,811 to 8,157 customers each).
- Test cutoff: 1 August 2026 (8,694 customers, 99 positives).
- June and July are excluded so their label windows do not overlap the test window.
- The early training cutoffs fall inside the history warm-up period. This is recorded as a limit.

### 5.4 Results (test cutoff, 1 August 2026)

| Measure | Full model | Without payment features |
|---|---|---|
| ROC-AUC (95% interval) | 0.906 (0.871 to 0.937) | 0.751 (0.702 to 0.799) |
| PR-AUC | 0.185 | 0.045 |
| Precision at top 1% review | 29.9% | 10.3% |
| Recall at top 1% review | 26.3% | 9.1% |

**Comparison with the frozen Phase 2 model:** 0.934 ROC-AUC (interval 0.908 to 0.955). The intervals overlap, so the rewrite is not clearly worse on ranking, but it is not better. Its purpose was to remove drift and to make the live model match the tested model.

**Calibration.** Predicted default rates are too low: average predicted 0.53% against an observed 1.14%. The top quintile predicts 2.1% against 4.9% observed. The model ranks customers usefully but does not estimate probabilities correctly. This is why the dashboard shows percentiles, not probabilities.

**Coefficients.** The strongest positive coefficient is the number of payment events in 90 days. This is largely a proxy for installment plans, which the generator assigns far more often to default-prone customers. This dependence is kept and documented.

---

## 6. Scoring engine (v2)

The scorer retrains the default model in the same run from the same training cutoffs, so there is no separate model file to manage.

| Score | Method |
|---|---|
| Default | Percentile rank among customers (0 to 100). Bands: High = top 1% (100 customers), Medium = next 9% (900), Low = rest (9,000) |
| Fraud | Unchanged rules: phone held by another account (60 points), two or more cancelled deals in the last 90 days (40 points). Bands: Low 0 to 39, Medium 40 to 69, High 70 and above |

**Fraud results match v1 exactly:** 9,379 low, 601 medium, 20 high.

**Explanations.** Each customer's top default factors are stored with their raw value and log-odds contribution. For high-band customers, the leading factor is payment activity (75 of 100) or missed-payment share (23 of 100). The uncalibrated probability is stored for monitoring only.

**Model version.** `lr-default-v2-trailing+rules-fraud-v1`. The v1 rows were removed when the data was regenerated, so score history starts at v2.

---

## 7. Shipment models: what was tested

The team asked for four additional models. Each was evaluated against the data, and the results determined what was built.

### 7.1 Delivery success

**Target:** delivered on the first attempt.

**Method:** logistic regression on features known at dispatch: account age, shared phone count, deals in the last 7 and 30 days, cancellations in the last 90 days, and route distance. Training used shipments before 1 June 2026; testing used mid-June to August.

**Result:** the first version had no discrimination, because its features did not describe the customer profiles. The corrected version was tested again and still showed no ability to rank shipments. The average predicted success matched the observed rate, but scores did not separate fraud actors from healthy customers.

**Decision:** not adopted. Delivery is reported as observed customer history, not as a prediction.

### 7.2 Failure reason

**Target:** the reason for a failed first attempt, trained only on failed shipments.

**Result:** accuracy 69.2%, the same as always predicting the most common reason (recipient unavailable). The model learned no pattern beyond the majority class.

**Decision:** not adopted. The observed reason mix is shown for each customer.

### 7.3 Expected delivery days (ETA)

**Method:** the median actual delivery time for each city pair, computed from training data.

**Result:** mean absolute error 0.64 days, against 0.65 days for the promised date. The estimate is not a meaningful improvement over the existing promise.

**Decision:** shown as a route estimate ("typical days for this route"), not a forecast, and compared with the promised date.

### 7.4 Return to origin (RTO)

**Result:** only 34 ordinary RTOs exist, plus 432 generated by the store-side rule. A learned model would mostly learn the rule.

**Decision:** not modeled. The number of store-marked deliveries that were returned is shown as a rule-based monitor for review.

### 7.5 Predictions table

The learned delivery and reason predictions were written to a separate table. Nothing reads that table now. Its removal is pending a decision (see section 12).

---

## 8. Dashboard changes

| Page or element | Change |
|---|---|
| Customer list and profile | Default score relabeled as a percentile, with a note explaining the High, Medium, and Low bands |
| Driver chart | Plain-language factor names replace internal feature names. The payment-activity label states that it includes installment plans |
| Score history chart | Fraud reference lines at 40 and 70. Default reference lines at 90 and 99 |
| Overview | Separate top-10 lists: one ranked by fraud score, one by default percentile. Scores from different scales are no longer merged |
| Overview | Note that store scores are not built yet |
| Store profile | "Not built yet" message; delivery caption updated; default score relabeled as a percentile |
| Customer profile | Observed shipment history panel: shipment count, first-attempt success, on-time rate, store-marked returns, failure reasons, and a warning when the sample is under 10 |
| Store pages | All stores show as Unscored |

---

## 9. API changes

### 9.1 Customer shipment summary (new endpoint)

Returns observed counts and rates for one customer's physical-goods shipments. It contains no predictions and no ground-truth fields. Store-marked deliveries are reported separately.

The endpoint was checked against the database on two customers: one with 24 shipments and two first-attempt failures, and one with 2 clean shipments. The counts matched the database exactly.

### 9.2 Shared API key

- Every endpoint requires an `X-API-Key` header, except the health check.
- The server fails closed: if no key is configured, protected endpoints refuse requests.
- The dashboard sends the key from its settings on every request.
- A single shared key is used. The team cannot be told apart by it.

### 9.3 Interactive documentation

The API documentation pages are off by default. They can be turned on locally with an environment setting.

### 9.4 Admin identity (unchanged)

The admin and viewer roles are still set by an unverified header, and the dashboard switch is cosmetic. This is a known limit and must be stated in the demo.

---

## 10. Testing

| Suite | Coverage | Status |
|---|---|---|
| API tests (Phase 3) | Read endpoints, actions, permissions, idempotency | Passing (34 tests) |
| Feature tests | Trailing-window features, no future data, outcome timing | Passing |
| API key tests | Health exemption, missing key, wrong key, fail-closed behavior, docs off | Added (5 tests) |
| Shipment endpoint tests | Counts, separation of store-marked deliveries, no ground-truth fields, empty customer, 404 | Added (4 tests) |
| Earlier Phase 2 tests | Superseded by the rewrite and removed | Removed |

**Still to do:** confirm the full suite passes in a clean run before the repository push. The dashboard has no automated tests and was checked by hand.

---

## 11. Repository and deployment preparation

**Repository.** The code is being pushed to the private repository. Excluded from the push: the virtual environment, test databases, the old demo database (to be regenerated), local secrets files, environment files, and caches.

**Demo database.** The demo database is to be regenerated with the final code, then committed once through Git LFS. Expected counts after regeneration: 152,607 deals, 221,585 transactions, 225,653 payment events, 80,380 shipments, and 10,000 customer scores under the v2 version.

**Hosting (planned):**

| Service | Settings |
|---|---|
| API (Render) | API key set as an environment variable; documentation off |
| Dashboard (Streamlit Community Cloud) | API address and API key stored in secrets; not committed |

Keys are not to be committed to the repository in any file.

---

## 12. Decisions made in this phase

| # | Decision | Reason |
|---|---|---|
| 1 | Extend the data (Path B) instead of using only the existing tables | The existing data had no delivery information |
| 2 | Keep the Phase 2 model design for the default rewrite | Keeps results comparable |
| 3 | Use trailing windows, not cumulative counts | Cumulative counts drift across time |
| 4 | Keep the installment dependence in the default model and document it | Removing it costs ranking, and the dependence is a known generator property |
| 5 | Show default scores as percentiles, not probabilities | Predicted probabilities are not calibrated |
| 6 | Keep the fraud rules unchanged | Confirmed by the team in an earlier phase |
| 7 | Do not adopt learned delivery, reason, or RTO models | No ability to rank or no data to learn from |
| 8 | Report ETA as a route estimate | Not a meaningful improvement on the promised date |
| 9 | Show a customer's observed shipment history instead of predictions | Facts with sample sizes are honest on this data |
| 10 | Leave store scores unbuilt | Deferred; stores show as Unscored |
| 11 | Use one shared API key, with docs off | Protects the write endpoints and the data without a login system |
| 12 | Defer deployment until local tests pass and the demo database is regenerated | Avoids deploying an out-of-date database |

**Pending decision:** drop the unused predictions table, or leave it empty and documented.

---

## 13. Known limitations

**Data and labels**
- All labels and patterns come from the generator's rules. Results describe the simulation, not real customers.
- Fraud actors are rare (158 customers, 874 deals). Fraud-related results are fragile.
- The history starts in November 2025. Early training cutoffs fall in the warm-up period.
- Shipment distances are approximate and hand-written.
- Store-marked returns are a generator rule. The RTO monitor measures the rule, not real behavior.
- The simulation ends on 15 November 2026; deals and shipments close near the end of the window are incomplete.

**Models**
- Default model ranking is good (ROC-AUC about 0.91), but its probabilities are underestimated by more than half.
- The default model depends on payment-event counts, largely as a proxy for installment plans.
- The default model is not clearly better than the frozen Phase 2 model, and the difference is within the uncertainty.
- The fraud model is two rules. Its thresholds were chosen and frozen in an earlier phase.
- Delivery success, failure reason, and RTO are not modeled. ETA is an estimate.
- The shared-phone feature includes accounts created after the shipment date (a small look-ahead). It is not used in the default model.
- Test results were checked on the same cutoff several times, so they confirm the design rather than providing an independent test.

**Platform and security**
- Admin identity is an unverified header. The Admin/Viewer switch does not restrict anything.
- A single shared API key is used. It cannot identify individual users.
- Admin actions and notes are not stored durably on the free hosting plan and reset on restart.
- The audit log is not enforced as append-only at the database level.
- The dashboard has no automated tests.
- Hosting is in a US region; this is acceptable only for synthetic data.
- Compliance (PDPL, SAMA) is out of scope for the prototype.

**Dashboard**
- Store scores are not built, so all stores show as Unscored.
- Store shipment statistics (delivery failures, refund figures) are not returned by the API.
- Score history holds one run per entity until the scoring job runs on a schedule.

---

## 14. Open items

**Before the team demo**
- [ ] Confirm the full test suite passes in a clean run.
- [ ] Decide whether to drop the unused predictions table.
- [ ] Remove unused scripts from the deployed repository, or move them to an archive folder with a note.
- [ ] Regenerate the demo database with the final code and confirm the counts.
- [ ] Set up the API hosting with the key as an environment variable.
- [ ] Set up the dashboard hosting with the API address and key in secrets.
- [ ] Smoke-test the deployed system: health check, unauthenticated request returns 401, dashboard loads with the key.
- [ ] Write the README (run instructions).
- [ ] Write the model card, recording all limits in section 13.
- [ ] Write the non-technical team report, stating what is synthetic and what is live.
- [ ] Write the demo script. It must state that all data is synthetic, scores are for demonstration only, the admin switch is cosmetic, and the team shares one key.

**After the demo (backlog)**
- [ ] Build store risk scores, when the team decides to.
- [ ] Regenerate the data with a pre-window warm-up, and retrain.
- [ ] Replace cumulative-free calibration with a monitored or fitted correction.
- [ ] Replace the shared key and the header identity with real login.
- [ ] Enforce the audit log as append-only.
- [ ] Add dashboard tests.
- [ ] Measure real distances for shipments.
- [ ] Revisit delivery and failure models if richer data is available.
- [ ] Replace the shared-phone look-ahead with an as-of count.

---

## 15. Reference numbers

| Item | Value |
|---|---|
| Customers | 10,000 (healthy 9,215; default-prone 627; fraud actor 158) |
| Stores | 500 (physical categories 282) |
| Deals | 152,607 |
| Transactions | 221,585 |
| Payment events | 225,653 |
| Fraud deals | 874 |
| Shipments | 80,380 (delivered 79,914; RTO 466) |
| Store-marked deliveries | 553 (of which 432 returned) |
| Default test ROC-AUC | 0.906 (v2 rewrite); 0.934 (frozen Phase 2) |
| Default bands | 100 high, 900 medium, 9,000 low |
| Fraud bands | 9,379 low, 601 medium, 20 high |
| Model version | lr-default-v2-trailing+rules-fraud-v1 |