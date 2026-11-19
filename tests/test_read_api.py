FORBIDDEN_FIELDS = ("default_label", "synthetic_profile", "is_fraud", "national_id_hash")


def assert_no_ground_truth(response) -> None:
    for field in FORBIDDEN_FIELDS:
        assert field not in response.text, f"{field} leaked in response"


# ---------- Customers ----------

def test_customer_list_returns_all_with_total(client, seeded):
    r = client.get("/customers")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert_no_ground_truth(r)


def test_customer_list_pagination(client):
    r = client.get("/customers", params={"limit": 2, "offset": 2})
    body = r.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 2
    assert len(body["items"]) == 1


def test_customer_search_by_name(client, seeded):
    r = client.get("/customers", params={"q": "alp"})
    items = r.json()["items"]
    assert [i["id"] for i in items] == [seeded["c1"]]


def test_latest_score_is_used(client, seeded):
    r = client.get(f"/customers/{seeded['c1']}")
    scores = r.json()["scores"]
    assert scores["default_score"] == 85
    assert scores["default_band"] == "high"


def test_unscored_customer_has_null_scores(client, seeded):
    r = client.get(f"/customers/{seeded['c3']}")
    assert r.json()["scores"] is None


def test_default_band_filter(client, seeded):
    high = client.get("/customers", params={"default_band": "high"}).json()["items"]
    low = client.get("/customers", params={"default_band": "low"}).json()["items"]
    assert [i["id"] for i in high] == [seeded["c1"]]
    assert [i["id"] for i in low] == [seeded["c2"]]


def test_sort_by_default_score_puts_nulls_last(client, seeded):
    r = client.get("/customers", params={"sort_by": "default_score", "order": "desc"})
    ids = [i["id"] for i in r.json()["items"]]
    assert ids == [seeded["c1"], seeded["c2"], seeded["c3"]]


def test_customer_detail_includes_recent_deals(client, seeded):
    r = client.get(f"/customers/{seeded['c1']}")
    body = r.json()
    assert len(body["recent_deals"]) == 1
    assert body["recent_deals"][0]["store_name"] == "Shop One"
    assert_no_ground_truth(r)


def test_customer_not_found(client):
    r = client.get("/customers/999999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Customer not found"


def test_invalid_limit_rejected(client):
    r = client.get("/customers", params={"limit": 0})
    assert r.status_code == 422


# ---------- Stores ----------

def test_store_list(client):
    r = client.get("/stores")
    assert r.json()["total"] == 2
    assert_no_ground_truth(r)


def test_store_filter_by_city(client, seeded):
    r = client.get("/stores", params={"city": "Jeddah"})
    assert [i["id"] for i in r.json()["items"]] == [seeded["s2"]]


def test_store_detail_stats(client, seeded):
    r = client.get(f"/stores/{seeded['s1']}")
    stats = r.json()["stats"]
    assert stats["total_deals"] == 2
    assert stats["disputed_deals"] == 1
    assert stats["dispute_rate"] == 0.5


def test_store_with_no_deals_has_null_dispute_rate(client, seeded):
    r = client.get(f"/stores/{seeded['s2']}")
    assert r.json()["stats"]["dispute_rate"] is None


def test_store_not_found(client):
    r = client.get("/stores/999999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Store not found"