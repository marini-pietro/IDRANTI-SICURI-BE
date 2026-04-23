"""
Tests for operator blueprint OPTIONS and input sanitization logic.
"""

import pytest
from marshmallow import ValidationError
from api_blueprints import operator_bp
from api_blueprints import blueprints_utils as bu

# This file contains unit tests for the Operator Blueprint defined in operator_bp.py


def test_operator_resource_options_and_validation():
    """
    Operator resource should return OPTIONS response with GET allowed.
    """

    cls = operator_bp.OperatorResource
    resp = bu.handle_options_request(cls)
    assert resp.status_code == 200
    assert "GET" in resp.headers["Allow"]


def test_operator_post_options():
    """
    Operator POST resource should return OPTIONS response with POST allowed.
    """

    cls = operator_bp.OperatorPostResource
    resp = bu.handle_options_request(cls)
    assert resp.status_code == 200
    assert "POST" in resp.headers["Allow"]


@pytest.mark.parametrize(
    "value", ["<script>alert(1)</script>", "javascript:evil()", "bad\x00name"]
)
def test_operator_safe_string_rejects_dangerous_values(value):
    """
    safe_string should reject common XSS and control-character payloads.
    """
    
    with pytest.raises(ValidationError):
        operator_bp.safe_string(value)


def test_operator_safe_string_accepts_clean_value():
    """safe_string should accept normal alphabetic values."""
    assert operator_bp.safe_string("Mario") == "Mario"
