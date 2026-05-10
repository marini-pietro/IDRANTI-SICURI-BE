"""
SQLAlchemy models representing database tables and providing serialization helpers.
"""

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import CITEXT, ENUM
# CITEXT is a case-insensitive text type, useful for email fields and similar use cases where case should not affect uniqueness or comparisons.
from sqlalchemy.orm import object_session

# Initialize SQLAlchemy instance
db = SQLAlchemy()


# Define ENUM types for relevant columns
hydrant_status_enum = ENUM(
    "Nuovo", "Buono","Discreto", "Pessimo", "Sconosciuto", name="stato_idrante_enum"
)
surface_enum = ENUM(
    "Asfalto", "Erba", "Terra base pietra", "Altro", name="superficie_enum"
)
positioning_enum = ENUM("Soprassuolo", "Sottosuolo", name="posizionamento_enum")
maintenance_status_enum = ENUM(
    "Buona", "Discreta", "Assente", name="stato_manutenzione_enum"
)
connection_diameter_enum = ENUM(
    "UNI 45", "UNI 70", "UNI 100", name="diametro_attacco_enum"
)
maintenance_type_enum = ENUM(
    "Controllo periodico di manutenzione ordinaria",
    "Manutenzione straordinaria",
    name="tipo_manutenzione_enum",
)
ruolo_enum = ENUM("amministratore", "ente", "visualizzatore", name="ruolo_enum")


class Entity(db.Model):
    """
    Represents a row from entities.
    """

    __tablename__ = "entities"

    entity_id = db.Column("entity_id", db.Integer, primary_key=True)
    denomination = db.Column(
        "denomination", db.String(255), unique=True, nullable=False
    )
    manager_email = db.Column("manager_email", CITEXT(), nullable=False)

    def to_dict(self):
        return {
            "entity_id": self.entity_id,
            "denomination": self.denomination,
            "manager_email": self.manager_email,
        }


class UserEntity(db.Model):
    """
    Association table between users and entities.
    """

    __tablename__ = "user_entities"

    user_email = db.Column("user_email", CITEXT(), primary_key=True)
    entity_id = db.Column("entity_id", db.Integer, primary_key=True)

    def to_dict(self):
        return {
            "user_email": self.user_email,
            "entity_id": self.entity_id,
        }


class User(db.Model):
    """
    Represents a row from users.
    """

    __tablename__ = "users"

    user_id = db.Column("user_id", db.Integer, primary_key=True)
    email = db.Column(CITEXT(), unique=True, nullable=False)
    first_name = db.Column("first_name", db.String(255), nullable=False)
    last_name = db.Column("last_name", db.String(255), nullable=False)
    password = db.Column("password", db.String(255), nullable=False)
    role = db.Column("role", ruolo_enum, nullable=False, default="visualizzatore")
    must_change_password = db.Column(
        "must_change_password", db.Boolean, nullable=False, default=True
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "amministratore"

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "role": self.role,
            "must_change_password": self.must_change_password,
        }


class Hydrant(db.Model):
    """Represents a row from hydrants."""

    __tablename__ = "hydrants"

    hydrant_id = db.Column("hydrant_id", db.Integer, primary_key=True)
    latitude = db.Column("latitude", db.Numeric(9, 6), nullable=False)
    longitude = db.Column("longitude", db.Numeric(9, 6), nullable=False)
    address = db.Column("address", db.String(255), nullable=False)
    status = db.Column(
        "status", hydrant_status_enum, nullable=False, default="Sconosciuto"
    )
    operational = db.Column("operational", db.Boolean, nullable=False, default=False)
    positioning = db.Column("positioning", positioning_enum, nullable=False)
    surface_type = db.Column("surface_type", surface_enum, nullable=False)
    leaks = db.Column("leaks", db.Boolean, nullable=False, default=False)
    has_sump = db.Column("has_sump", db.Boolean, nullable=False, default=False)
    accessible_firetruck = db.Column(
        "accessible_firetruck", db.Boolean, nullable=False, default=False
    )
    maintenance_status = db.Column(
        "maintenance_status", maintenance_status_enum, nullable=False, default="Assente"
    )
    entity_id = db.Column(
        "entity_id", db.Integer, db.ForeignKey("entities.entity_id"), nullable=False
    )

    def to_dict(self):
        return {
            "hydrant_id": self.hydrant_id,
            "latitude": float(self.latitude),
            "longitude": float(self.longitude),
            "address": self.address,
            "status": self.status,
            "operational": self.operational,
            "positioning": self.positioning,
            "surface_type": self.surface_type,
            "leaks": self.leaks,
            "has_sump": self.has_sump,
            "accessible_firetruck": self.accessible_firetruck,
            "maintenance_status": self.maintenance_status,
            "entity_id": self.entity_id,
        }


class Connector(db.Model):
    """
    Represents a row from connectors.
    """

    __tablename__ = "connectors"

    hydrant_id = db.Column(
        "hydrant_id", db.Integer, db.ForeignKey("hydrants.hydrant_id"), primary_key=True
    )
    diameter = db.Column("diameter", connection_diameter_enum, primary_key=True)
    cap_missing = db.Column("cap_missing", db.Boolean, nullable=False, default=False)
    chain_missing = db.Column(
        "chain_missing", db.Boolean, nullable=False, default=False
    )

    def to_dict(self):
        return {
            "hydrant_id": self.hydrant_id,
            "diameter": self.diameter,
            "cap_missing": self.cap_missing,
            "chain_missing": self.chain_missing,
        }


class Photo(db.Model):
    """
    Represents a row from photo.
    """

    __tablename__ = "photo"

    photo_id = db.Column("id_foto", db.Integer, primary_key=True)
    hydrant_id = db.Column(
        "hydrant_id", db.Integer, db.ForeignKey("hydrants.hydrant_id"), nullable=False
    )
    path = db.Column("path", db.String(1024), nullable=False)

    def to_dict(self):
        return {
            "photo_id": self.photo_id,
            "hydrant_id": self.hydrant_id,
            "path": self.path,
        }


class Maintenance(db.Model):
    """
    Represents a row from maintenance.
    """

    __tablename__ = "maintenance"

    maintenance_id = db.Column("maintenance_id", db.Integer, primary_key=True)
    hydrant_id = db.Column(
        "hydrant_id", db.Integer, db.ForeignKey("hydrants.hydrant_id"), nullable=False
    )
    user_email = db.Column(
        "user_email", CITEXT(), db.ForeignKey("users.email"), nullable=False
    )
    maintenance_timestamp = db.Column(
        "maintenance_timestamp", db.DateTime, nullable=False, default=func.now()
    )
    type_ = db.Column("type", maintenance_type_enum, nullable=False)
    # type is a reserved keyword in Python, so to avoid overwriting the built-in add a trailing underscore

    outcome = db.Column("outcome", db.Boolean, nullable=False)
    notes = db.Column("notes", db.Text)

    def to_dict(self):
        timestamp_value = self.maintenance_timestamp
        if isinstance(timestamp_value, datetime):
            timestamp_value = timestamp_value.isoformat(sep=" ")

        return {
            "maintenance_id": self.maintenance_id,
            "hydrant_id": self.hydrant_id,
            "user_email": self.user_email,
            "maintenance_timestamp": timestamp_value,
            "type": self.type_,
            "outcome": self.outcome,
            "notes": self.notes,
        }
