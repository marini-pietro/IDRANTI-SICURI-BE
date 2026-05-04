"""
Tests for user blueprint helper functions and login proxy behavior.
"""

import pytest
from marshmallow import ValidationError
from api_blueprints import user_bp
from api_blueprints import blueprints_utils as bu
from api_server import main_api

# This file contains unit tests for the User Blueprint defined in user_bp.py


def test_hash_password_format():
    """
    hash_password should return a non-empty salt:hash formatted string.
    """

    hp = user_bp.hash_password("secret123")

    # The result should be a string containing a salt and hash separated by a colon
    assert isinstance(hp, str)
    assert ":" in hp
    salt, hashed = hp.split(":", 1)
    assert salt != "" and hashed != ""


def test_user_login_forwards_request(monkeypatch):
    """
    UserLogin should forward credentials and return auth-service tokens.
    """

    monkeypatch.setattr(user_bp, "LOGIN_AVAILABLE_THROUGH_API", True)

    # Simulate auth service returning OK
    class DummyResp:
        status_code = 200

        def json(self):
            return {"access_token": "tok", "refresh_token": "rtok"}

    def fake_post(url, json=None, timeout=None):
        return DummyResp()

    monkeypatch.setattr(user_bp, "requests_post", fake_post)

    # Use the app's request context to provide JSON body
    with main_api.test_request_context(json={"email": "u@x.com", "password": "p"}):
        resp = user_bp.UserLogin().post()

        # The response should have status 200 and include
        # the access token from the dummy auth service
        assert resp.status_code == bu.STATUS_CODES["ok"]
        assert resp.get_json()["access_token"] == "tok"


def test_user_login_handles_unauthorized(monkeypatch):
    """
    UserLogin should map unauthorized responses from auth service.
    """

    monkeypatch.setattr(user_bp, "LOGIN_AVAILABLE_THROUGH_API", True)

    class DummyResp:
        status_code = bu.STATUS_CODES["unauthorized"]

        def json(self):
            return {}

    def fake_post(url, json=None, timeout=None):
        return DummyResp()

    # Patch the requests_post function to return an unauthorized response
    monkeypatch.setattr(user_bp, "requests_post", fake_post)

    # Use the app's request context to provide JSON body
    with main_api.test_request_context(json={"email": "u@x.com", "password": "p"}):
        resp = user_bp.UserLogin().post()
        assert resp.status_code == bu.STATUS_CODES["unauthorized"]


def test_hash_password_uses_random_salt():
    """
    Two hashes of the same password should differ because salts are random.
    """

    # Hash the same password twice and verify that the
    # outputs are different due to random salts
    h1 = user_bp.hash_password("same-password")
    h2 = user_bp.hash_password("same-password")
    assert h1 != h2


@pytest.mark.parametrize("value", ["<script>", "javascript:evil()", "name\x1f"])
def test_user_safe_string_rejects_dangerous_input(value):
    """
    safe_string should reject script-like and control-character payloads.
    """

    with pytest.raises(ValidationError):
        user_bp.safe_string(value)


def test_user_login_handles_upstream_timeout(monkeypatch):
    """
    UserLogin should return internal error if auth service is unavailable.
    """

    monkeypatch.setattr(user_bp, "LOGIN_AVAILABLE_THROUGH_API", True)

    def fake_post(_url, json=None, timeout=None):
        raise user_bp.RequestException("timeout")

    monkeypatch.setattr(user_bp, "requests_post", fake_post)

    # Use the app's request context to provide JSON body
    with main_api.test_request_context(json={"email": "u@x.com", "password": "p"}):
        resp = user_bp.UserLogin().post()

    # The response should have status 500 Internal Server Error due to the simulated timeout
    assert resp.status_code == bu.STATUS_CODES["internal_server_error"]
