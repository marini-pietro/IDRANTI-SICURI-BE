"""
Unit tests for SQLAlchemy model serialization helpers in models.py.
"""

from datetime import datetime
from models import Connector, Entity, Hydrant, Maintenance, Photo, User


def test_hydrant_to_dict_contains_expected_fields():
    """
    Hydrant.to_dict should expose the current hydrant columns.
    """

    hydrant = Hydrant(
        hydrant_id=10,
        latitude=45.4642,
        longitude=9.19,
        address="Via Roma, Milano",
        status="Nuovo",
        operational=True,
        positioning="Soprassuolo",
        surface_type="Asfalto",
        leaks=False,
        has_sump=True,
        accessible_firetruck=True,
        maintenance_status="Buona",
        entity_id=1,
    )

    data = hydrant.to_dict()
    assert data["hydrant_id"] == 10
    assert data["address"] == "Via Roma, Milano"
    assert data["entity_id"] == 1


def test_user_to_dict_contains_identity_and_role_fields():
    """
    User.to_dict should include identity fields and derived role.
    """

    user = User(
        user_id=3,
        email="john@example.com",
        first_name="John",
        last_name="Doe",
        password="hashed",
        role="visualizzatore",
        must_change_password=True,
    )

    data = user.to_dict()
    assert data["user_id"] == 3
    assert data["email"] == "john@example.com"
    assert data["role"] == "visualizzatore"


def test_entity_to_dict_contains_name_and_responsible_email():
    """
    Entity.to_dict should preserve the entity name and responsible email.
    """

    entity = Entity(
        entity_id=7, denomination="Comune di Roma", manager_email="admin@comune.it"
    )

    data = entity.to_dict()
    assert data == {
        "entity_id": 7,
        "denomination": "Comune di Roma",
        "manager_email": "admin@comune.it",
    }


def test_photo_to_dict_serializes_path_and_hydrant_id():
    """
    Photo.to_dict should include the stored path and hydrant id.
    """

    photo = Photo(
        photo_id=3,
        hydrant_id=10,
        path="foto/10-1.png",
    )

    data = photo.to_dict()
    assert data["hydrant_id"] == 10
    assert data["path"] == "foto/10-1.png"


def test_maintenance_to_dict_serializes_timestamp_and_outcome():
    """
    Maintenance.to_dict should expose the UTC timestamp and outcome.
    """

    maintenance = Maintenance(
        maintenance_id=8,
        hydrant_id=10,
        user_email="john@example.com",
        maintenance_timestamp=datetime(2026, 4, 20, 12, 30, 0),
        type_="Controllo periodico di manutenzione ordinaria",
        outcome=True,
        notes="ok",
    )

    data = maintenance.to_dict()
    assert data["maintenance_id"] == 8
    assert data["outcome"] is True


def test_connector_to_dict_serializes_composite_key_fields():
    """
    Connector.to_dict should expose the hydrant/dimension composite key.
    """

    connector = Connector(
        hydrant_id=10, diameter="UNI 45", cap_missing=False, chain_missing=True
    )

    data = connector.to_dict()
    assert data == {
        "hydrant_id": 10,
        "diameter": "UNI 45",
        "cap_missing": False,
        "chain_missing": True,
    }
