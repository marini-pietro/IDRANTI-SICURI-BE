"""
This module defines the database models for the application using SQLAlchemy.
It includes the following models:
- Hydrant: Represents a fire hydrant with attributes such as status, location, type,
    accessibility, and the email of the person who inserted it.
- User: Represents a user of the application with attributes such as email, municipality,
    name, surname, password, and role (admin, operator, viewer).
- Operator: Represents an operator with attributes such as tax code (CF), name, and surname.
- Photo: Represents a photo of a hydrant with attributes such as photo
    ID, date, hydrant ID, and position.
- Control: Represents a control check on a hydrant with attributes such as
    control ID, date, type, outcome, and hydrant ID.
Each model includes a to_dict method for easy serialization to a dictionary format.
The module also initializes the SQLAlchemy database instance that will be used
to interact with the database throughout the application.
"""

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import ENUM

db = SQLAlchemy()


class Hydrant(db.Model):
    """
    Represents a fire hydrant in the database.
    """

    __tablename__ = "idranti"
    id = db.Column(db.Integer, primary_key=True)
    stato = db.Column(db.String, nullable=False)
    latitudine = db.Column(db.Float, nullable=False)
    longitudine = db.Column(db.Float, nullable=False)
    comune = db.Column(db.String, nullable=False)
    via = db.Column(db.String, nullable=False)
    area_geo = db.Column(db.String, nullable=False)
    tipo = db.Column(db.String, nullable=False)
    accessibilita = db.Column(db.String, nullable=False)
    email_ins = db.Column(db.String, nullable=False)

    def to_dict(self):
        """
        Convert the Hydrant object to a dictionary for easy serialization.
        """

        return {
            "id": self.id,
            "stato": self.stato,
            "latitudine": self.latitudine,
            "longitudine": self.longitudine,
            "comune": self.comune,
            "via": self.via,
            "area_geo": self.area_geo,
            "tipo": self.tipo,
            "accessibilita": self.accessibilita,
            "email_ins": self.email_ins,
        }


user_role_enum = ENUM("admin", "operator", "viewer", name="user_role")


class User(db.Model):
    """
    Represents a user of the application in the database.
    """

    __tablename__ = "utenti"
    email = db.Column(db.String, primary_key=True)
    comune = db.Column(db.String, nullable=False)
    nome = db.Column(db.String, nullable=False)
    cognome = db.Column(db.String, nullable=False)
    password = db.Column(db.String, nullable=False)
    ruolo = db.Column(user_role_enum, nullable=False, default="viewer")

    def to_dict(self):
        """
        Convert the User object to a dictionary for easy serialization.
        """
        return {
            "email": self.email,
            "comune": self.comune,
            "nome": self.nome,
            "cognome": self.cognome,
            "password": self.password,
            "ruolo": self.ruolo,
        }


class Operator(db.Model):
    """
    Represents an operator in the database.
    """

    __tablename__ = "operatori"
    CF = db.Column(db.String(16), primary_key=True)
    nome = db.Column(db.String, nullable=False)
    cognome = db.Column(db.String, nullable=False)

    def to_dict(self):
        """
        Convert the Operator object to a dictionary for easy serialization.
        """
        return {
            "CF": self.CF,
            "nome": self.nome,
            "cognome": self.cognome,
        }


class Photo(db.Model):
    """
    Represents a photo of a hydrant in the database.
    """

    __tablename__ = "foto"
    id_foto = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    id_idrante = db.Column(db.Integer, db.ForeignKey("idranti.id"), nullable=False)
    posizione = db.Column(db.String, nullable=False)

    def to_dict(self):
        """
        Convert the Photo object to a dictionary for easy serialization.
        """
        return {
            "id_foto": self.id_foto,
            "data": self.data,
            "id_idrante": self.id_idrante,
            "posizione": self.posizione,
        }


class Control(db.Model):
    """
    Represents a control check on a hydrant in the database.
    """

    __tablename__ = "controlli"
    id_controllo = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    tipo = db.Column(db.String, nullable=False)
    esito = db.Column(db.Boolean, nullable=False)
    id_idrante = db.Column(db.Integer, db.ForeignKey("idranti.id"), nullable=False)

    def to_dict(self):
        """
        Convert the Control object to a dictionary for easy serialization.
        """
        return {
            "id_controllo": self.id_controllo,
            "data": self.data,
            "tipo": self.tipo,
            "esito": self.esito,
            "id_idrante": self.id_idrante,
        }
