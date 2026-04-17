import pytest
from api_server import is_input_safe, API_VERSION, STATUS_CODES
import api_server

# This file contains unit tests for the functions and features defined in api_server.py


# Parametrized test for is_input_safe function (test function will be called once for each tuple in the list)
@pytest.mark.parametrize(
    "value,expected",
    [
        ("hello world", True),
        ("SELECT * FROM users WHERE id=1", False),
        (["one", "two"], True),
        ({"key": "value"}, True),
        ({"drop": "DROP TABLE"}, False),
        (
            "",
            True,
        ),  # empty string should be treated as safe (depending on implementation)
        (None, True),  # non-string types can be allowed; adjust if behaviour differs
    ],
)
def test_is_input_safe_various(value, expected):
    # Parametrized checks for different inputs to `is_input_safe`.
    assert is_input_safe(value) is expected


def test_rate_limit_enforced(client, monkeypatch):
    # Enable rate limiting and force is_rate_limited to return True
    monkeypatch.setattr(api_server, "API_SERVER_RATE_LIMIT", True)
    monkeypatch.setattr(api_server, "is_rate_limited", lambda ip: True)
    resp = client.get(f"/api/{API_VERSION}/health")
    assert resp.status_code == STATUS_CODES["too_many_requests"]
    assert resp.get_json() == {"error": "Rate limit exceeded"}


def test_rate_limit_not_enforced_when_disabled(client, monkeypatch):
    # Disable rate limiting even if is_rate_limited would return True
    monkeypatch.setattr(api_server, "API_SERVER_RATE_LIMIT", False)
    monkeypatch.setattr(api_server, "is_rate_limited", lambda ip: True)
    resp = client.get(f"/api/{API_VERSION}/health")
    assert resp.status_code == STATUS_CODES["ok"]
    assert resp.get_json() == {"status": "ok"}


def test_health_check_endpoint(client):
    # Uses the test client fixture to call the health endpoint and verify response
    resp = client.get(f"/api/{API_VERSION}/health")
    assert resp.status_code == STATUS_CODES["ok"]
    assert resp.get_json() == {"status": "ok"}
