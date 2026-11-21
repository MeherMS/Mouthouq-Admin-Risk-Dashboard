import pytest
from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture
def bare_client():
    # No default headers, so requests carry no API key.
    return TestClient(app)


def test_health_is_public(bare_client):
    assert bare_client.get("/health").status_code == 200


def test_protected_route_rejects_missing_key(bare_client):
    assert bare_client.get("/customers").status_code == 401


def test_protected_route_rejects_wrong_key(bare_client):
    r = bare_client.get("/customers", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_fails_closed_when_server_key_unset(bare_client, monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    r = bare_client.get("/customers", headers={"X-API-Key": "test-key"})
    assert r.status_code == 503


def test_docs_are_off_by_default(bare_client):
    assert bare_client.get("/docs").status_code == 404
    assert bare_client.get("/openapi.json").status_code == 404