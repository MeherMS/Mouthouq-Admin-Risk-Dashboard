import pandas as pd

from app.ml.features import ALL_FEATURES, DEFAULT_FEATURES, build_customer_features


def T(s):
    return pd.Timestamp(s)


CUTOFF = T("2026-06-01")


def make_tables():
    customers = pd.DataFrame({
        "id": [1, 2, 3],
        "phone": ["A", "A", "A"],  # customer 3 shares the phone but joins after the cutoff
        "created_at": [T("2026-01-01"), T("2026-02-01"), T("2026-07-01")],
    })
    deals = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "customer_id": [1, 1, 2, 1, 2],
        "status": ["paid", "cancelled", "disputed", "paid", "cancelled"],
        "amount_sar": [100.0, 200.0, 300.0, 50.0, 80.0],
        "created_at": [T("2026-05-10"), T("2026-05-20"), T("2026-03-01"),
                       T("2026-06-05"), T("2026-05-01")],
        "closed_at": [pd.NaT, T("2026-05-25"), T("2026-03-10"),
                      pd.NaT, T("2026-06-15")],  # deal 5 closes after the cutoff
    })
    transactions = pd.DataFrame({"id": [1, 2, 3, 4], "deal_id": [1, 2, 3, 4]})
    payment_events = pd.DataFrame({
        "transaction_id": [1, 1, 3, 4],
        "event_type": ["on_time", "late", "missed", "missed"],
        "occurred_at": [T("2026-05-10"), T("2026-05-30"),
                        T("2026-04-01"), T("2026-06-10")],  # last one is after the cutoff
    })
    return {
        "customers": customers,
        "deals": deals,
        "transactions": transactions,
        "payment_events": payment_events,
    }


def truncate(tables, cutoff):
    """Keep only rows that existed before the cutoff."""
    customers = tables["customers"][tables["customers"]["created_at"] < cutoff]
    deals = tables["deals"][tables["deals"]["created_at"] < cutoff]
    transactions = tables["transactions"][tables["transactions"]["deal_id"].isin(deals["id"])]
    events = tables["payment_events"][
        tables["payment_events"]["occurred_at"].lt(cutoff)
        & tables["payment_events"]["transaction_id"].isin(transactions["id"])
    ]
    return {
        "customers": customers,
        "deals": deals,
        "transactions": transactions,
        "payment_events": events,
    }


def test_known_values():
    feats = build_customer_features(make_tables(), CUTOFF)
    assert list(feats.index) == [1, 2]  # customer 3 joins after the cutoff
    assert feats.loc[1, "account_age_days"] == 151
    assert feats.loc[1, "shared_phone_count"] == 1  # customer 3 must not count
    assert feats.loc[1, "deals_30d"] == 2
    assert feats.loc[1, "deals_90d"] == 2  # deal 4 is after the cutoff
    assert feats.loc[1, "events_90d"] == 2
    assert feats.loc[1, "cancel_rate_90d"] == 1.0
    assert feats.loc[2, "missed_share_90d"] == 1.0
    assert feats.loc[2, "dispute_rate_90d"] == 1.0  # deal 5 closes after the cutoff


def test_rows_after_cutoff_do_not_change_features():
    full = make_tables()
    expected = build_customer_features(truncate(full, CUTOFF), CUTOFF)
    actual = build_customer_features(full, CUTOFF)
    pd.testing.assert_frame_equal(actual, expected)


def test_outcome_closing_after_cutoff_is_ignored():
    base = build_customer_features(make_tables(), CUTOFF)
    for closed in [T("2026-06-20"), pd.NaT]:
        tables = make_tables()
        tables["deals"].loc[tables["deals"]["id"] == 5, "closed_at"] = closed
        pd.testing.assert_frame_equal(build_customer_features(tables, CUTOFF), base)


def test_shape_and_no_nans():
    feats = build_customer_features(make_tables(), CUTOFF)
    assert list(feats.columns) == ALL_FEATURES
    assert "shared_phone_count" not in DEFAULT_FEATURES
    assert not feats.isna().any().any()