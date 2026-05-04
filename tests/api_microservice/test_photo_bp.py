"""
Tests for photo blueprint OPTIONS behavior and validation helpers.
"""

import pytest
from marshmallow import ValidationError
from api_blueprints import photo_bp
from api_blueprints import blueprints_utils as bu

# This file contains unit tests for the Photo Blueprint defined in photo_bp.py


def test_photo_resource_options():
    """
    Photo resource should expose GET in Allow header.
    """

    cls = photo_bp.PhotoResource
    resp = bu.handle_options_request(cls)

    # The response should have status 200 and include an Allow header with GET method
    assert resp.status_code == 200
    assert "GET" in resp.headers["Allow"]


def test_photo_post_options():
    """
    Photo POST resource should expose POST in Allow header.
    """

    cls = photo_bp.PhotoPostResource
    resp = bu.handle_options_request(cls)

    # The response should have status 200 and include an Allow header with POST method
    assert resp.status_code == 200
    assert "POST" in resp.headers["Allow"]


def test_photo_safe_string_rejects_dangerous_values():
    """
    safe_string should reject strings with script payload markers.
    """

    with pytest.raises(ValidationError):
        photo_bp.safe_string("javascript:alert(1)")


def test_photo_schema_requires_positive_hydrant_id():
    """
    Photo schema should reject non-positive hydrant IDs.
    """

    payload = {"id_idrante": 0, "posizione": "foto/1.png", "data": "2026-01-31"}
    with pytest.raises(ValidationError):
        photo_bp.photo_schema.load(payload)
