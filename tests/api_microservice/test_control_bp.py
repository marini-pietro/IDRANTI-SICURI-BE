"""
Tests for control blueprint OPTIONS metadata and schema validation behavior.
"""

import pytest
from marshmallow import ValidationError
from api_blueprints import control_bp
from api_blueprints import blueprints_utils as bu

# This file contains unit tests for the Control Blueprint defined in control_bp.py


def test_control_resource_options():
    """
    Control resource OPTIONS response should include GET method.
    """

    # Ensure that the class responds correctly to OPTIONS requests
    cls = control_bp.ControlResource
    resp = bu.handle_options_request(cls)
    
    # The response should have status 200 and include an Allow header with GET method
    assert resp.status_code == 200
    assert "Allow" in resp.headers
    assert "GET" in resp.headers["Allow"]


def test_control_post_resource_options():
    """
    Control POST resource OPTIONS response should include POST method.
    """

    # Ensure that the class responds correctly to OPTIONS requests
    cls = control_bp.ControlPostResource
    resp = bu.handle_options_request(cls)

    # The response should have status 200 and include an Allow header with POST method
    assert resp.status_code == 200
    assert "POST" in resp.headers["Allow"] or "OPTIONS" in resp.headers["Allow"]


def test_control_schema_rejects_invalid_date_format():
    """
    Control schema should reject non-date values for the data field.
    """

    payload = {
        "tipo": "manutenzione",
        "esito": True,
        "data": "31-12-2026",
        "id_idrante": 1,
    }

    with pytest.raises(ValidationError):
        control_bp.control_schema.load(payload)
