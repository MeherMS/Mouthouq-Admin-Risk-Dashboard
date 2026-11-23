# Admin Risk Dashboard: Project Report

*Prepared for non-technical readers. All data in this project is synthetic (computer-generated), so no figure describes a real customer or store.*

---

## 1. Summary

The project is a prototype dashboard for a Saudi payment platform. It helps an admin see which customers and stores may be risky, and it records every action the admin takes. The prototype runs on simulated data because real customer data cannot be used at this stage.

The dashboard tracks two different kinds of risk for each customer:

- **Fraud risk:** the customer plans to cheat the platform from the start.
- **Default risk:** the customer wants to pay but runs into financial trouble.

The project also includes delivery-related outputs for physical goods. These are more limited than the two risk scores, and most were tested and found not reliable enough to use as predictions (see Section 6).

The prototype is a demonstration. It is not ready for real decisions.

---

## 2. Why the project exists

Payment platforms lose money when customers do not pay or when people use the platform to commit fraud. The team wanted a single screen where an admin could see risk levels, understand the main reasons behind them, and take action with a clear record.

The team chose to keep fraud and default separate. They have different causes and need different signals, so combining them into one number would hide useful information.

---

## 3. The data

Because real customer data was not available for the prototype, the team built a simulator. It creates a fictional population and simulates a year of activity. The simulator was designed so that the two risk patterns appear in the data, which lets the team test whether the scoring methods can detect them.

**Scale of the simulated data:**

| Item | Count |
|---|---|
| Customers | 10,000 |
| Stores | 500 |
| Purchases (deals) | 152,607 |
| Payment transactions | 221,585 |
| Payment events (on-time, late, missed, and similar) | 225,653 |
| Shipments (physical-goods stores only) | 80,380 |

**Customer types in the simulation:**

| Type | Count | Share |
|---|---|---|
| Healthy | 9,215 | about 92% |
| Default-prone | 627 | about 6% |
| Fraud actor | 158 | about 1.6% |

**Store types:** 444 legitimate, 36 with high dispute rates, and 20 fraud stores.

Two points matter for interpreting results:

- **The simulator decides the answers.** The team defined which customers default and which commit fraud. A model that scores well on this data has learned the simulator's rules. Real behavior will differ.
- **Some patterns were designed in.** For example, fraud actors are more likely to have new accounts and to share phone numbers. Real fraud may look different.

---

## 4. The two risk scores

### 4.1 Fraud risk

Fraud is scored with a simple set of transparent rules, not a learned model. The rules were kept unchanged throughout the project.

- If a phone number is shared with another account: 60 points.
- If the customer has two or more cancelled purchases in the last 90 days: 40 points.

Scores are capped at 100. Bands are Low (0 to 39), Medium (40 to 69), and High (70 to 100).

Results on the simulated data: 9,379 customers Low, 601 Medium, and 20 High.

Earlier attempts to add other fraud signals, such as rapid purchase activity and disputes, did not show a useful effect on the training data, so they were not used.

### 4.2 Default risk

Default risk uses a statistical model called logistic regression. It looks at a customer's recent history over the last 30 and 90 days, including:

- How often they pay late, partially, or not at all
- How many purchases they made and cancelled
- The size of their purchases
- How long their account has existed

The model does not estimate the actual chance of default. Its predicted percentages were too low compared with the observed rates. So the dashboard shows each customer's **rank** instead:

- **High:** the top 1% of customers (100 customers)
- **Medium:** the next 9% (900 customers)
- **Low:** the remaining 9,000 customers

**How well it ranks:** On a test period (August 2026), the model's ranking score was 0.906, where 1.0 is perfect and 0.5 is no better than chance. An earlier version scored 0.934, but the team rebuilt the model so it uses only information available at the time of each prediction. The two scores overlap within their uncertainty, so the rebuilt model is not clearly better or worse. Its main benefit is that it can be explained and reproduced.

**Important limit:** A large part of the model's signal comes from the number of payment events. This is largely because the simulator gives installment plans more often to default-prone customers. In real life, a customer with many payments is not necessarily a higher risk.

---

## 5. Explanations and the dashboard

For each customer, the dashboard shows the main factors behind the default score, in plain language (for example, "payment activity" or "share of missed payments"). Each factor is shown with the customer's own value, so an admin can see why a customer ranks high.

The dashboard has these main pages:

- **Overview:** how many customers and stores fall into each band, trends over time, and two separate top-10 lists, one for fraud and one for default.
- **Customers:** a searchable list, a detailed profile for each customer, the scores and their history, shipment history, transactions, and recent purchases.
- **Stores:** a list and profile for each store, including dispute and refund figures. Store risk scores are not built yet, so all stores show as "unscored."
- **Action log:** a record of every admin action and note, with filters.

Admins can freeze or unfreeze customers, approve or reject stores, flag records for review, and add notes. Each action requires a reason of at least three characters and a confirmation step on the dashboard. The action is also saved to an audit trail.

---

## 6. Delivery outputs: what was tested and where things stand

The team planned four delivery-related outputs. Shipments exist only for physical-goods stores (electronics, furniture, fashion, and automotive).

Each output was tested against the simulated data. The results determined what the prototype shows.

| Output | What the team wanted | What was tested | What the prototype shows now |
|---|---|---|---|
| **Delivery success** | A percentage showing how likely a delivery is to succeed | A learned model predicting first-attempt success | **Observed history, not a prediction.** For each customer, the dashboard shows the share of their deliveries that succeeded on the first attempt, with the number of shipments. A learned model could not tell customer groups apart, so it was not used. |
| **RTO (return to origin)** | A prediction of which orders will be returned | Checked whether enough returns existed to learn from | **No model.** There were only 34 ordinary returns in the data, too few to learn from. A rule counts deliveries that the store marked as delivered but were returned, which measures the simulator's own rule. |
| **ETA (expected delivery time)** | A prediction of how many days delivery will take | A city-pair estimate compared with the promised delivery date | **Route estimate only.** The estimate for each route is shown next to the promised date. It was not meaningfully more accurate than the promised date (average error of 0.64 days against 0.65 days). |
| **Failure reason** | A prediction of why a delivery failed (for example, recipient unavailable) | A learned model trained on failed deliveries | **Observed mix, not a prediction.** The dashboard shows each customer's reasons for failed deliveries. The learned model reached 69.2% accuracy, which equals always guessing the most common reason. |

Two points about the delivery data:

- **Distances between cities are hand-written approximations**, not measured distances.
- **The simulator generates a set of store-marked returns**, so the RTO monitor mainly reflects the simulator's rule, not real behavior.

**Status check:** The project documents record these outputs as "not adopted" or "route estimate only." If the team is now building learned delivery models, the status needs to be updated.

---

## 7. Infrastructure and deployment

- **Backend (API):** An interface that the dashboard uses to read data and submit actions. It is the only layer the dashboard talks to.
- **Database:** A single-file database, set up so it can later move to a larger system.
- **Hosting:** The team planned a demo on free hosting. The backend was reported as deployed, and the dashboard was reported as in progress. The most recent document says hosting is still being set up, so the current status should be confirmed.
- **Access:** A single shared key protects the API. The admin and viewer roles are set by an unverified header, so anyone can switch roles. The team should not expose the system beyond trusted people.
- **Demo data:** Admin actions and notes are lost when the hosted service restarts. The data itself stays fixed.

---

## 8. Known limits

**About the data**
- Every result describes the simulator, not real customers.
- Fraud is rare in the data (158 customers, 874 purchases), so fraud results are not stable.
- The simulated history starts in November 2025, so early training periods are partly incomplete.
- The simulation ends on 15 November 2026. Recent purchases and shipments are incomplete.

**About the models**
- The default model ranks customers reasonably but does not estimate probabilities accurately.
- The model depends on payment activity, which partly reflects how the simulator was designed.
- The test period was used several times during development, so the results confirm the design but do not prove it on new data.
- The fraud model is a set of rules, not a learned model.

**About security and compliance**
- The admin roles are not verified.
- One shared key is used, so the system cannot tell individual users apart.
- The audit log is not yet protected against changes at the database level.
- The project has not been reviewed against Saudi data-protection requirements (PDPL) or banking-sector rules (SAMA). These must be addressed before real use.

---

## 9. Next steps

From the project documents, the main open items are:

1. Confirm that the team demo runs on the hosted system, and write a demo script.
2. Add stronger access control (verified logins instead of the header-based roles).
3. Build the batch scoring job that writes regular, versioned scores.
4. Decide what to do with the unused predictions table.
5. Regenerate the data with a longer warm-up period and retrain the models.
6. Decide whether to build store risk scores.
7. Review the delivery outputs if richer or real shipment data becomes available.
8. Address compliance before any production use.

---

## 10. Glossary

- **Synthetic data:** Simulated data created by a program, used because real data is not available.
- **Default:** When a customer cannot pay what they owe.
- **Fraud:** Deliberate deception to obtain goods or money without paying.
- **Percentile:** A customer's position in the ranking, where the top 1% is the highest-risk group.
- **RTO (return to origin):** A delivery that goes back to the store instead of reaching the customer.
- **ETA:** Estimated time of arrival, here the expected number of days for delivery.
- **Model:** A calculation that turns past data into a score for future behavior.
- **Audit trail:** A permanent record of who did what and when.

