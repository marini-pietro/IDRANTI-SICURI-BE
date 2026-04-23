"""
Tests for helper decorators and response utilities in blueprints_utils.
"""

import pytest
from flask import Response
from api_blueprints import blueprints_utils as bu
from api_server import main_api

# This file contains unit tests for the functions defined in blueprints_utils.py


def test_create_response_valid():
    """create_response should return a JSON Flask response for dict payloads."""
    # create_response uses Flask's current_app, so we need to get an app context from Flask
    # Gotcha: jsonify()/make_response rely on an application context (not a request context).
    # Using app_context() is sufficient. If you use request data inside
    # create_response in the future, switch to test_request_context().
    with main_api.app_context():
        resp = bu.create_response({"hello": "world"}, 200)
        # Basic shape and status
        assert isinstance(resp, Response)
        assert resp.status_code == 200

        # Small improvement: ensure Content-Type is JSON. Without this,
        # Flask's resp.get_json() may return None (it relies on a JSON
        # content type by default).
        assert "application/json" in resp.content_type

        # Confirm the payload round-trips through Flask's JSON helpers
        assert resp.get_json() == {"hello": "world"}


def test_create_response_type_errors():
    """create_response should reject unsupported payload/status types."""
    # Non-dict payloads should raise TypeError
    with pytest.raises(TypeError):
        bu.create_response("not a dict", 200)
    with pytest.raises(TypeError):
        bu.create_response({"ok": 1}, "200")
    # Also ensure lists containing non-dicts are rejected
    with pytest.raises(TypeError):
        bu.create_response([{"ok": 1}, "bad_item"], 200)


def test_get_hateos_location_string():
    """
    HATEOAS helper should include scheme and resource path.
    """
    
    # Ensure the function returns a correctly formatted string
    loc = bu.get_hateos_location_string("/hydrants", 123)
    assert isinstance(loc, str)
    assert "://" in loc and "/hydrants/123" in loc


def test_handle_options_request_class():
    """
    OPTIONS helper should publish Allow header for class methods.
    """

    # Check that a dummy class passed to handle_options_request produces a correctly
    # formed response
    class Dummy:
        get = lambda self: None
        post = lambda self: None

    resp = bu.handle_options_request(Dummy)
    assert resp.status_code == 200
    assert "Allow" in resp.headers


def test_handle_options_request_type_error():
    """
    Passing an instance instead of a class should raise TypeError.
    """

    # Passing a non-class should raise TypeError
    with pytest.raises(TypeError):
        bu.handle_options_request(object())


# Additional small-improvement tests
def test_create_response_accepts_list_of_dicts():
    """
    create_response should support lists of dictionaries as JSON payloads.
    """

    # create_response explicitly allows a list of dicts.
    # Verify JSON array behavior and status code.
    with main_api.app_context():
        payload = [{"a": 1}, {"b": 2}]
        resp = bu.create_response(payload, 200)
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        assert resp.get_json() == payload


def test_jwt_validation_required_missing_token_returns_unauthorized():
    """
    JWT decorator should return 401 when no token is provided anywhere.
    """

    @bu.jwt_validation_required
    def endpoint():
        return {"ok": True}, 200

    with main_api.test_request_context("/", method="GET"):
        body, status = endpoint()

    assert status == bu.STATUS_CODES["unauthorized"]
    assert body == {"error": "missing token"}


def test_check_authorization_rejects_invalid_role():
    """
    Authorization decorator should reject tokens carrying unsupported roles.
    """

    @bu.check_authorization(["admin"])
    def endpoint(**_kwargs):
        return {"ok": True}, 200

    with main_api.app_context():
        resp = endpoint(role="not-a-role")

    assert resp.status_code == bu.STATUS_CODES["bad_request"]
    assert resp.get_json() == {"error": "invalid user role"}


def test_check_authorization_allows_expected_role():
    """
    Authorization decorator should allow execution for permitted roles.
    """

    @bu.check_authorization(["admin", "operator"])
    def endpoint(**_kwargs):
        return {"ok": True}, 200

    result = endpoint(role="operator")
    assert result == ({"ok": True}, 200)
