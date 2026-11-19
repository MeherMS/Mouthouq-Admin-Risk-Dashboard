from app.models import Action, AuditLog
from tests.conftest import count_rows


def freeze_url(customer_id):
    return f"/customers/{customer_id}/freeze"


# ---------- Access control ----------

def test_missing_header_returns_401(client, seeded):
    r = client.post(freeze_url(seeded["c1"]), json={"reason": "test reason"})
    assert r.status_code == 401


def test_unknown_admin_id_returns_401(client, seeded):
    r = client.post(
        freeze_url(seeded["c1"]),
        json={"reason": "test reason"},
        headers={"X-Admin-Id": "99999"},
    )
    assert r.status_code == 401


def test_viewer_gets_403(client, seeded, viewer_headers):
    r = client.post(
        freeze_url(seeded["c1"]),
        json={"reason": "test reason"},
        headers=viewer_headers,
    )
    assert r.status_code == 403
    assert count_rows(Action) == 0


# ---------- Validation ----------

def test_short_reason_rejected(client, seeded, admin_headers):
    r = client.post(freeze_url(seeded["c1"]), json={"reason": "ab"}, headers=admin_headers)
    assert r.status_code == 422


def test_whitespace_only_reason_rejected(client, seeded, admin_headers):
    r = client.post(freeze_url(seeded["c1"]), json={"reason": "     "}, headers=admin_headers)
    assert r.status_code == 422


def test_unknown_customer_returns_404(client, admin_headers):
    r = client.post(freeze_url(999999), json={"reason": "test reason"}, headers=admin_headers)
    assert r.status_code == 404
    assert r.json()["detail"] == "Customer not found"


# ---------- Freeze / unfreeze ----------

def test_freeze_changes_status_and_writes_logs(client, seeded, admin_headers):
    r = client.post(freeze_url(seeded["c1"]),
                    json={"reason": "suspicious activity"},
                    headers=admin_headers)
    body = r.json()
    assert r.status_code == 200
    assert body["changed"] is True
    assert body["account_status"] == "frozen"
    assert body["action_id"] is not None

    assert client.get(f"/customers/{seeded['c1']}").json()["account_status"] == "frozen"
    assert count_rows(Action) == 1
    assert count_rows(AuditLog) == 1


def test_audit_payload_records_before_and_after(client, seeded, admin_headers):
    client.post(freeze_url(seeded["c1"]), json={"reason": "test reason"}, headers=admin_headers)

    from tests.conftest import SessionLocal
    db = SessionLocal()
    try:
        entry = db.query(AuditLog).one()
        assert entry.event == "customer.freeze"
        assert entry.admin_id == seeded["admin"]
        assert entry.payload["status_before"] == "active"
        assert entry.payload["status_after"] == "frozen"
        assert entry.payload["reason"] == "test reason"
    finally:
        db.close()


def test_freeze_is_idempotent_and_writes_nothing_extra(client, seeded, admin_headers):
    client.post(freeze_url(seeded["c1"]), json={"reason": "test reason"}, headers=admin_headers)
    r = client.post(freeze_url(seeded["c1"]), json={"reason": "test reason"}, headers=admin_headers)

    assert r.status_code == 200
    assert r.json()["changed"] is False
    assert r.json()["action_id"] is None
    assert count_rows(Action) == 1
    assert count_rows(AuditLog) == 1


def test_unfreeze_active_customer_is_noop(client, seeded, admin_headers):
    r = client.post(f"/customers/{seeded['c1']}/unfreeze",
                    json={"reason": "test reason"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["changed"] is False
    assert r.json()["account_status"] == "active"
    assert count_rows(Action) == 0


def test_unfreeze_pending_customer_returns_409(client, seeded, admin_headers):
    from app.models import AccountStatus, Customer
    from tests.conftest import SessionLocal

    db = SessionLocal()
    try:
        customer = db.get(Customer, seeded["c1"])
        customer.account_status = AccountStatus.PENDING
        db.commit()
    finally:
        db.close()

    r = client.post(f"/customers/{seeded['c1']}/unfreeze",
                    json={"reason": "test reason"}, headers=admin_headers)
    assert r.status_code == 409
    assert "expected frozen" in r.json()["detail"]
    assert count_rows(Action) == 0


def test_unfreeze_after_freeze(client, seeded, admin_headers):
    client.post(freeze_url(seeded["c1"]), json={"reason": "test reason"}, headers=admin_headers)
    r = client.post(f"/customers/{seeded['c1']}/unfreeze",
                    json={"reason": "cleared on review"}, headers=admin_headers)
    assert r.json()["changed"] is True
    assert r.json()["account_status"] == "active"
    assert count_rows(Action) == 2


# ---------- Flag review and notes ----------

def test_flag_review_twice_in_a_row_is_noop(client, seeded, admin_headers):
    url = f"/customers/{seeded['c1']}/flag-review"
    first = client.post(url, json={"reason": "velocity spike"}, headers=admin_headers)
    second = client.post(url, json={"reason": "velocity spike"}, headers=admin_headers)

    assert first.json()["changed"] is True
    assert second.json()["changed"] is False
    assert count_rows(Action) == 1


def test_notes_always_create_rows(client, seeded, admin_headers):
    url = f"/customers/{seeded['c1']}/notes"
    first = client.post(url, json={"reason": "called customer"}, headers=admin_headers)
    second = client.post(url, json={"reason": "called customer"}, headers=admin_headers)

    assert first.json()["changed"] is True
    assert second.json()["changed"] is True
    assert first.json()["action_id"] != second.json()["action_id"]
    assert count_rows(Action) == 2


def test_note_does_not_change_account_status(client, seeded, admin_headers):
    r = client.post(f"/customers/{seeded['c1']}/notes",
                    json={"reason": "called customer"}, headers=admin_headers)
    assert r.json()["account_status"] == "active"


# ---------- Stores ----------

def test_reject_then_approve_store(client, seeded, admin_headers):
    r = client.post(f"/stores/{seeded['s2']}/reject",
                    json={"reason": "missing documents"}, headers=admin_headers)
    assert r.json()["account_status"] == "rejected"

    r = client.post(f"/stores/{seeded['s2']}/approve",
                    json={"reason": "documents received"}, headers=admin_headers)
    assert r.json()["changed"] is True
    assert r.json()["account_status"] == "active"


def test_approve_already_active_store_is_noop(client, seeded, admin_headers):
    r = client.post(f"/stores/{seeded['s1']}/approve",
                    json={"reason": "re-check"}, headers=admin_headers)
    assert r.json()["changed"] is False
    assert count_rows(Action) == 0


def test_store_action_on_unknown_store(client, admin_headers):
    r = client.post("/stores/999999/reject",
                    json={"reason": "test reason"}, headers=admin_headers)
    assert r.status_code == 404
    assert r.json()["detail"] == "Store not found"


def test_customer_approve_route_does_not_exist(client, seeded, admin_headers):
    r = client.post(f"/customers/{seeded['c1']}/approve",
                    json={"reason": "test reason"}, headers=admin_headers)
    assert r.status_code in (404, 405)