"""
Tests for hydrant blueprint metadata, OPTIONS behavior, and schema validation.
"""

from marshmallow import ValidationError
from api_blueprints import hydrant_bp
from api_blueprints import blueprints_utils as bu

# This file contains unit tests for the Hydrant Blueprint defined in hydrant_bp.py


def test_hydrant_resource_endpoints_and_options():
    """
    Hydrant resource should expose endpoint paths and OPTIONS metadata.
    """

    # Ensure class defines endpoint paths
    cls = hydrant_bp.HydrantResource
    assert hasattr(cls, "ENDPOINT_PATHS")

    # Use handle_options_request on the class
    resp = bu.handle_options_request(cls)
    assert resp.status_code == 200
    assert "Allow" in resp.headers

    # Should at least include GET and OPTIONS
    assert "GET" in resp.headers["Allow"]
    assert "OPTIONS" in resp.headers["Allow"]


def test_hydrant_post_resource_options():
    """
    Hydrant POST resource should advertise POST in Allow header.
    """

    cls = hydrant_bp.HydrantPostResource
    resp = bu.handle_options_request(cls)

    # The response should have status 200
    assert resp.status_code == 200

    # Ensure POST is allowed for the POST resource's OPTIONS response
    assert "POST" in resp.headers["Allow"]


def test_hydrant_schema_rejects_invalid_latitudine_type():
    """
    Hydrant schema should reject non-float latitude values.
    """

    payload = {
        "latitude": 45.4642,
        "longitude": 9.19,
        "address": "Via Roma, Milano",
        "status": "Nuovo",
        "operational": True,
        "positioning": "Soprassuolo",
        "surface": "Asfalto",
        "leaks": False,
        "has_pit": True,
        "truck_access": True,
        "maintenance_status": "Buona",
        "entity_id": 1,
    }

    payload["latitude"] = "not-a-number"

    try:
        hydrant_bp.hydrant_schema.load(payload)
        assert False, "Expected schema validation to fail"
    except ValidationError as exc:
        assert "latitude" in exc.messages
