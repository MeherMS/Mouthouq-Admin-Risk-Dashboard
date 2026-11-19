import pandas as pd

from app.ml.population import drop_customers


def test_drop_customers_removes_only_listed_ids():
    df = pd.DataFrame({"customer_id": [1, 2, 3, 4], "default_label": [0, 1, 0, 1]})
    out = drop_customers(df, {2, 4})
    assert out["customer_id"].tolist() == [1, 3]


def test_dropping_negatives_keeps_positives():
    df = pd.DataFrame({"customer_id": [1, 2, 3, 4], "default_label": [0, 1, 0, 1]})
    out = drop_customers(df, {1, 3})  # both have label 0
    assert out["default_label"].sum() == df["default_label"].sum()


def test_empty_drop_list_returns_all_rows():
    df = pd.DataFrame({"customer_id": [1, 2], "default_label": [0, 1]})
    assert len(drop_customers(df, set())) == 2