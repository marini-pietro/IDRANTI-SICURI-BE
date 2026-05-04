"""
Unit tests for SQLAlchemy model serialization helpers in models.py.
"""

from datetime import date
from models import Hydrant, User, Operator, Photo, Control


def test_hydrant_to_dict_contains_expected_fields():
    """
    Hydrant.to_dict should expose all modeled hydrant fields.
    """

    hydrant = Hydrant(
        id=10,
        stato="attivo",
        latitudine=45.4642,
        longitudine=9.1900,
        comune="Milano",
        via="Via Roma",
        area_geo="Centro",
        tipo="soprasuolo",
        accessibilita="pubblica",
        email_ins="user@example.com",
    )

    data = hydrant.to_dict()
    assert data["id"] == 10
    assert data["email_ins"] == "user@example.com"


def test_user_to_dict_contains_identity_and_role_fields():
    """
    User.to_dict should include core user identity and role fields.
    """

    user = User(
        email="john@example.com",
        comune="Milano",
        nome="John",
        cognome="Doe",
        password="hashed",
        ruolo="viewer",
    )

    data = user.to_dict()
    assert data["email"] == "john@example.com"
    assert data["ruolo"] == "viewer"


def test_operator_to_dict_contains_cf_and_names():
    """
    Operator.to_dict should preserve CF and name attributes.
    """

    operator = Operator(CF="RSSMRA80A01F205X", nome="Mario", cognome="Rossi")

    data = operator.to_dict()
    assert data == {
        "CF": "RSSMRA80A01F205X",
        "nome": "Mario",
        "cognome": "Rossi",
    }


def test_photo_to_dict_serializes_date_and_hydrant_id():
    """
    Photo.to_dict should include date, hydrant id and position.
    """

    photo = Photo(
        id_foto=3,
        data=date(2026, 4, 23),
        id_idrante=10,
        posizione="foto/10-1.png",
    )

    data = photo.to_dict()
    assert data["id_idrante"] == 10
    assert str(data["data"]) == "2026-04-23"


def test_control_to_dict_serializes_boolean_result():
    """
    Control.to_dict should expose boolean esito as-is.
    """

    control = Control(
        id_controllo=8,
        data=date(2026, 4, 20),
        tipo="manutenzione",
        esito=True,
        id_idrante=10,
    )

    data = control.to_dict()
    assert data["id_controllo"] == 8
    assert data["esito"] is True
