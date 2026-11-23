"""
Read-only database overview for the Database Guide page.

Returns table descriptions, row counts, relationships, and simple statistics.
Never returns personal identifiers, row-level data, or synthetic-only values.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.api.deps import get_db

# CONFIRM: if your other read routers apply the API key per router instead of
# globally in main.py, add the same dependency here, e.g.
# router = APIRouter(prefix="/database", tags=["database"], dependencies=[Depends(require_api_key)])
router = APIRouter(prefix="/database", tags=["database"])


TABLE_NOTES = {
    "customers": "People who buy on credit through the platform. One customer can have many deals.",
    "stores": "Shops and service providers that sell through the platform.",
    "deals": "A purchase agreement between one customer and one store. This is the central record.",
    "transactions": "A payment attempt made for a deal (card, bank transfer, or installment). One deal can have several.",
    "payment_events": "What happened to each payment over time, such as on time, late, missed, partial, refunded, or charged back.",
    "risk_scores": "Risk scores for customers and stores, kept as history. Each scoring run adds rows. The newest row is the current score.",
    "actions": "Decisions taken by admins (freeze, unfreeze, approve, reject, flag for review, note). One row per action.",
    "audit_log": "A record of admin activity, meant to be add-only. Used to trace who changed what and when.",
    "users": "Dashboard login accounts. Each has a role: admin or viewer.",
    "shipments": "Physical deliveries for goods stores (electronics, furniture, fashion, automotive).",
}

COLUMN_NOTES = {
    "customers.id": "Unique customer number.",
    "customers.name": "Customer name (synthetic data).",
    "customers.national_id_hash": "Scrambled version of the national ID. The raw ID is never stored.",
    "customers.phone": "Phone number. Two or more accounts sharing a number can indicate linked accounts.",
    "customers.email": "Email address.",
    "customers.city": "City of residence.",
    "customers.created_at": "Date the account was opened.",
    "customers.account_status": "Account state: active, frozen, or pending.",
    "deals.id": "Unique deal number.",
    "deals.customer_id": "The customer who made the deal.",
    "deals.store_id": "The store where the deal was made.",
    "deals.amount_sar": "Deal value in Saudi riyals.",
    "deals.status": "Stage of the deal: opened, paid, delivered, cancelled, or disputed.",
    "deals.created_at": "When the deal was opened.",
    "deals.closed_at": "When the deal was closed, if it has been.",
    "transactions.deal_id": "The deal this payment belongs to.",
    "transactions.method": "How the customer paid: card, bank transfer, or installment.",
    "transactions.status": "Result of the payment attempt.",
    "transactions.failure_reason": "Why the payment failed, if it did.",
    "payment_events.transaction_id": "The payment this event belongs to.",
    "payment_events.event_type": "What happened: on time, late, missed, partial, chargeback, or refund.",
    "payment_events.occurred_at": "When the event happened.",
    "risk_scores.entity_type": "Whether the score is for a customer or a store.",
    "risk_scores.entity_id": "The customer or store this score belongs to.",
    "risk_scores.fraud_score": "Fraud risk from 0 to 100. Higher means more risk.",
    "risk_scores.default_score": "Default risk, shown as a percentile among customers (0 to 100).",
    "risk_scores.fraud_band": "Fraud risk group: Low, Medium, or High.",
    "risk_scores.default_band": "Default risk group: Low, Medium, or High.",
    "risk_scores.model_version": "Which model or rule set produced the score.",
    "risk_scores.top_factors": "Main reasons behind the score, stored as structured text.",
    "risk_scores.computed_at": "When the score was calculated.",
    "actions.entity_type": "Whether the action was on a customer or a store.",
    "actions.entity_id": "The customer or store the action was taken on.",
    "actions.action_type": "What was done: freeze, approve, reject, flag, or note.",
    "actions.reason": "The reason the admin entered.",
    "actions.admin_id": "The admin who took the action.",
    "actions.created_at": "When the action was taken.",
    "audit_log.admin_id": "The admin who made the change.",
    "audit_log.event": "Name of the event that was recorded.",
    "audit_log.payload": "Details of the change, stored as structured text.",
    "audit_log.timestamp": "When the change was recorded.",
    "users.role": "Access level: admin (can act) or viewer (read only).",
}

# Fields created only for the synthetic data generator. They are shown as
# labeled in the schema, but their values and statistics are never shown.
SYNTHETIC_ONLY = {
    "customers.default_label",
    "customers.synthetic_profile",
    "deals.is_fraud",
}

# Links that exist by convention but are not enforced by the database.
SOFT_LINKS = [
    {
        "from_table": "risk_scores",
        "column": "entity_id",
        "targets": ["customers", "stores"],
    },
    {
        "from_table": "actions",
        "column": "entity_id",
        "targets": ["customers", "stores"],
    },
]

# (title, table, column). Entries are skipped automatically if the column is missing.
STAT_SPECS = [
    ("Customers by account status", "customers", "account_status"),
    ("Stores by category", "stores", "category"),
    ("Stores by account status", "stores", "account_status"),
    ("Deals by status", "deals", "status"),
    ("Transactions by payment method", "transactions", "method"),
    ("Payment events by type", "payment_events", "event_type"),
    ("Risk scores by model version", "risk_scores", "model_version"),
    ("Actions by type", "actions", "action_type"),
    ("Shipments by final status", "shipments", "final_status"),  # CONFIRM column name
]


def _key_role(column_name, primary_keys, foreign_keys):
    parts = []
    if column_name in primary_keys:
        parts.append("Primary key")
    if column_name in foreign_keys:
        parts.append(f"Link to {foreign_keys[column_name]}")
    return ", ".join(parts)


def _group_counts(conn, existing, table, column):
    if table not in existing or column not in existing[table]:
        return None
    rows = conn.execute(
        text(
            f'SELECT "{column}", COUNT(*) FROM "{table}" '
            f'GROUP BY "{column}" ORDER BY COUNT(*) DESC'
        )
    ).all()
    return [
        {"label": "(not set)" if value is None else str(value), "count": int(count)}
        for value, count in rows
    ]


def _headline(conn, existing):
    items = []

    def has(table, column):
        return table in existing and column in existing[table]

    if "deals" in existing:
        total = conn.execute(text('SELECT COUNT(*) FROM "deals"')).scalar() or 0
        items.append({"label": "Deals recorded", "value": f"{total:,}"})

        if has("deals", "status") and total:
            disputed = conn.execute(
                text("SELECT COUNT(*) FROM deals WHERE status = 'disputed'")
            ).scalar() or 0
            items.append({"label": "Share of deals disputed", "value": f"{disputed / total:.1%}"})

        if has("deals", "amount_sar") and total:
            avg = conn.execute(text("SELECT AVG(amount_sar) FROM deals")).scalar() or 0
            items.append({"label": "Average deal value", "value": f"{avg:,.0f} SAR"})

        if has("deals", "created_at") and total:
            first, last = conn.execute(
                text("SELECT MIN(created_at), MAX(created_at) FROM deals")
            ).one()
            items.append({"label": "Deals cover", "value": f"{str(first)[:10]} to {str(last)[:10]}"})

    if "transactions" in existing:
        total_tx = conn.execute(text('SELECT COUNT(*) FROM "transactions"')).scalar() or 0
        if has("transactions", "failure_reason") and total_tx:
            failed = conn.execute(
                text("SELECT COUNT(*) FROM transactions WHERE failure_reason IS NOT NULL")
            ).scalar() or 0
            items.append({"label": "Payments with a failure reason", "value": f"{failed / total_tx:.1%}"})

    if "customers" in existing:
        total_c = conn.execute(text('SELECT COUNT(*) FROM "customers"')).scalar() or 0
        items.append({"label": "Customers", "value": f"{total_c:,}"})

    if "stores" in existing:
        total_s = conn.execute(text('SELECT COUNT(*) FROM "stores"')).scalar() or 0
        items.append({"label": "Stores", "value": f"{total_s:,}"})

    return items[:4]


@router.get("/overview")
def database_overview(db: Session = Depends(get_db)):
    conn = db.connection()
    insp = inspect(conn)

    table_names = sorted(insp.get_table_names())
    columns_by_table = {t: insp.get_columns(t) for t in table_names}
    existing = {t: {c["name"] for c in cols} for t, cols in columns_by_table.items()}
    row_counts = {
        t: conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar() or 0
        for t in table_names
    }

    tables = []
    relations = []

    for t in table_names:
        primary_keys = insp.get_pk_constraint(t).get("constrained_columns", [])

        foreign_keys = {}
        for fk in insp.get_foreign_keys(t):
            for col in fk["constrained_columns"]:
                foreign_keys[col] = fk["referred_table"]
            relations.append({
                "from_table": t,
                "to_table": fk["referred_table"],
                "column": ", ".join(fk["constrained_columns"]),
            })

        columns = []
        for c in columns_by_table[t]:
            key = f"{t}.{c['name']}"
            columns.append({
                "field": c["name"],
                "meaning": COLUMN_NOTES.get(key, "No plain description yet."),
                "type": str(c["type"]),
                "key": _key_role(c["name"], primary_keys, foreign_keys),
                "synthetic_only": key in SYNTHETIC_ONLY,
            })

        tables.append({
            "name": t,
            "title": t.replace("_", " ").capitalize(),
            "purpose": TABLE_NOTES.get(t, "No plain description yet."),
            "row_count": row_counts[t],
            "columns": columns,
        })

    soft_links = [
        {
            "from_table": s["from_table"],
            "column": s["column"],
            "targets": [target for target in s["targets"] if target in existing],
        }
        for s in SOFT_LINKS
        if s["from_table"] in existing
    ]

    statistics = []
    for title, table, column in STAT_SPECS:
        rows = _group_counts(conn, existing, table, column)
        if rows is not None:
            statistics.append({"title": title, "table": table, "column": column, "rows": rows})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": {
            "tables": len(tables),
            "total_rows": sum(row_counts.values()),
            "relationships": len(relations),
            "synthetic_only_fields": len(SYNTHETIC_ONLY),
        },
        "tables": tables,
        "relations": relations,
        "soft_links": soft_links,
        "headline": _headline(conn, existing),
        "statistics": statistics,
    }