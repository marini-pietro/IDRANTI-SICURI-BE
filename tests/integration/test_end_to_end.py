"""
Simple integration tests that exercise auth and api endpoints without
requiring a real database or external services.

These tests verify:
- auth health endpoint returns ok
- protected API endpoint requires JWT and returns 401 when missing
- auth login returns 400 for empty payloads
"""

from api_server import main_api
from auth_server import auth_api
from configs.api_config import API_VERSION, STATUS_CODES


def test_auth_health_check():
    client = auth_api.test_client()
    resp = client.get("/health")
    assert resp.status_code == STATUS_CODES["ok"]
    assert resp.get_json().get("status") == "ok"


def test_api_protected_endpoint_requires_token():
    client = main_api.test_client()
    # call protected endpoint without any JWT
    resp = client.post(f"/api/{API_VERSION}/logs/clear", json={"timestamp": "2025-01-01 00:00:00"})
    assert resp.status_code == STATUS_CODES["unauthorized"]
    body = resp.get_json()
    assert isinstance(body, dict)
    assert body.get("error") == "missing token"


def test_auth_login_empty_payload_returns_bad_request():
    client = auth_api.test_client()
    resp = client.post(f"/auth/{API_VERSION}/login", json={})
    assert resp.status_code == STATUS_CODES["bad_request"]
