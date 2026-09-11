"""Living server health shape (no long sim)."""
from __future__ import annotations

from living_server.app import STATE, create_app
from starlette.testclient import TestClient


def test_living_health_json_shape():
    STATE.engine = None
    app = create_app(None)
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "living_city"
    assert body["living"] is True
    assert "freellm" in body
    assert "tick" in body


def test_agents_503_without_engine():
    STATE.engine = None
    app = create_app(None)
    client = TestClient(app)
    r = client.get("/v1/agents")
    assert r.status_code == 503
