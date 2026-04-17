"""
Blueprint for operator-related API endpoints.
Provides CRUD operations for operator resources identified by their CF.
"""

# Library imports
from os.path import basename as os_path_basename
from re import match as re_match
from re import search as re_search
from re import IGNORECASE as re_IGNORECASE
from typing import Dict, Union, Any
from flask import Blueprint, request, Response
from flask_restful import Api, Resource
from flask_jwt_extended import jwt_required
from marshmallow import fields, ValidationError

# Local imports
from models import db, Operator
from api_server import ma
from api_config import (
    STATUS_CODES,
)
from .blueprints_utils import (
    check_authorization,
    log,
    create_response,
    get_hateos_location_string,
    handle_options_request,
)

# Define constants
BP_NAME = os_path_basename(__file__).replace("_bp.py", "")

# Create the blueprint and API
operator_bp = Blueprint(BP_NAME, __name__)
api = Api(operator_bp)


# Define schemas and validation function
def safe_string(value):
    """
    Custom validation function to ensure that a string does not
    contain potentially dangerous characters.
    Checks for the presence of "<", ">", "javascript:" and control characters.
    If the string contains any of these, a ValidationError is raised.
    This helps to prevent injection attacks and XSS vulnerabilities.
    If the string is valid, it is returned unchanged.
    """

    if not isinstance(value, str):
        raise ValidationError("Must be a string.")
    if (
        "<" in value
        or ">" in value
        or re_search(r"javascript:|[\x00-\x1F\x7F]", value, re_IGNORECASE)
    ):
        raise ValidationError("Invalid characters in string.")
    return value


class OperatorSchema(ma.Schema):
    """
    Marshmallow schema for validating and serializing Operator data.
    Defines the expected fields for an Operator resource, including:
    - CF: A required string field representing the operator's
      unique identifier (16-character alphanumeric string).
    - nome: A required string field representing the operator's first name,
      validated to ensure it does not contain potentially dangerous characters.
    - cognome: A required string field representing the operator's last name,
      also validated for safety.
    """

    CF = fields.String(required=True)
    nome = fields.String(required=True, validate=safe_string)
    cognome = fields.String(required=True, validate=safe_string)


# Instantiate the schema
operator_schema = OperatorSchema()


class OperatorResource(Resource):
    """
    Resource for managing operators.
    This class provides methods to get, update, and delete operator records by their CF.
    """

    ENDPOINT_PATHS = [f"/{BP_NAME}/<string:CF>"]

    @jwt_required()
    def get(self, CF, identity) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Get operator by CF
        description: Retrieve operator information from the database by CF
        (16-character alphanumeric string).
        operationId: getOperatorByCF
        security:
          - bearerAuth: []
        parameters:
          - name: CF
            in: path
            required: true
            description: The unique identifier (CF) of the operator to retrieve.
            schema:
              type: string
              example: RSSMRA80A01F205X
        responses:
          200:
            description: Operator found
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    CF:
                      type: string
                      example: RSSMRA80A01F205X
                    nome:
                      type: string
                      example: Mario
                    cognome:
                      type: string
                      example: Rossi
          400:
            description: Invalid CF
          404:
            description: Operator not found
        """

        # Validate the CF
        if not isinstance(CF, str) or not re_match(r"^[A-Z0-9]{16}$", CF):
            return create_response(
                message={"error": "CF must be a 16-character alphanumeric string."},
                status_code=STATUS_CODES["bad_request"],
            )

        # Get the data
        operator: Operator = Operator.query.filter_by(CF=CF).first()

        # Check if the result is empty
        if operator is None:
            return create_response(
                message={"error": "no resource found with specified cf"},
                status_code=STATUS_CODES["not_found"],
            )

        # Log the action
        log(
            message=f"User {identity} fetched operator with cf {CF}",
            level="INFO",
            message_id="OPRGET",
            sd_tags={
                "endpoint": request.path,
                "method": request.method,
                "identity": identity,
                "operator_cf": CF,
            },
        )

        # Return the operator as a JSON response
        return create_response(
            message=operator_schema.dump(operator), status_code=STATUS_CODES["ok"]
        )

    @jwt_required()
    def patch(self, CF, identity) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Update an operator by CF
        description: Update an existing operator record by CF. Allows partial updates.
        operationId: updateOperatorByCF
        security:
          - bearerAuth: []
        parameters:
          - name: CF
            in: path
            required: true
            description: The unique identifier (CF) of the operator to update.
            schema:
              type: string
              example: RSSMRA80A01F205X
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  CF:
                    type: string
                    example: RSSMRA80A01F205X
                  nome:
                    type: string
                    example: Mario
                  cognome:
                    type: string
                    example: Rossi
        responses:
          200:
            description: Operator updated
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    outcome:
                      type: string
                      example: successfully updated operator
                    location:
                      type: string
                      example: /operator/RSSMRA80A01F205X
          400:
            description: Invalid input
          404:
            description: Operator not found
        """

        # Load input data
        try:
            data = operator_schema.load(
                request.get_json(), partial=True
            )  # partial=True to allow partial updates
        except ValidationError as err:
            return create_response(
                message={"error": err.messages},
                status_code=STATUS_CODES["bad_request"],
            )

        # Validate the CF
        if not isinstance(CF, str) or not re_match(r"^[A-Z0-9]{16}$", CF):
            return create_response(
                message={"error": "CF must be a 16-character alphanumeric string."},
                status_code=STATUS_CODES["bad_request"],
            )

        # Check that the operator exists
        operator: Operator = Operator.query.filter_by(CF=CF).first()
        if operator is None:
            return create_response(
                message={"error": "no resource found with specified cf"},
                status_code=STATUS_CODES["not_found"],
            )

        # Log the action
        log(
            message=f"User {identity} updated operator with cf {CF}",
            level="INFO",
            message_id="OPRPATCH",
            sd_tags={
                "endpoint": request.path,
                "method": request.method,
                "identity": identity,
                "operator_cf": CF,
            },
        )

        # Update only provided fields
        if "CF" in data and data["CF"]:
            operator.CF = data["CF"]
        if "nome" in data and data["nome"]:
            operator.nome = data["nome"]
        if "cognome" in data and data["cognome"]:
            operator.cognome = data["cognome"]

        # Commit the changes to the database
        db.session.commit()

        # Return the response
        return create_response(
            message={
                "outcome": "successfully updated operator",
                "location": get_hateos_location_string(
                    bp_name=BP_NAME, id_=operator.CF
                ),
            },
            status_code=STATUS_CODES["ok"],
        )

    @jwt_required()
    def delete(self, CF, identity) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Delete an operator by CF
        description: Delete an operator record from the database by CF.
        operationId: deleteOperatorByCF
        security:
          - bearerAuth: []
        parameters:
          - name: CF
            in: path
            required: true
            description: The unique identifier (CF) of the operator to delete.
            schema:
              type: string
              example: RSSMRA80A01F205X
        responses:
          200:
            description: Operator deleted
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    outcome:
                      type: string
                      example: successfully deleted operator
          400:
            description: Invalid CF
          404:
            description: Operator not found
        """

        # Validate the CF
        if not isinstance(CF, str) or not re_match(r"^[A-Z0-9]{16}$", CF):
            return create_response(
                message={"error": "CF must be a 16-character alphanumeric string."},
                status_code=STATUS_CODES["bad_request"],
            )

        # Check if the operator exists
        operator: Operator = Operator.query.filter_by(CF=CF).first()
        if operator is None:
            return create_response(
                message={"error": "no resource found with specified cf"},
                status_code=STATUS_CODES["not_found"],
            )

        # Log the action
        log(
            message=f"User {identity} deleted operator with cf {CF}",
            level="INFO",
            message_id="OPRDEL",
            sd_tags={
                "endpoint": request.path,
                "method": request.method,
                "identity": identity,
                "operator_cf": CF,
            },
        )

        # Delete the operator
        db.session.delete(operator)

        # Commit the changes to the database
        db.session.commit()

        # Return the response
        return create_response(
            message={"outcome": "successfully deleted operator"},
            status_code=STATUS_CODES["ok"],
        )

    @jwt_required()
    def options(self) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Get allowed HTTP methods for operator resource
        description: Returns the allowed HTTP methods for the operator resource endpoint.
        operationId: optionsOperator
        security:
          - bearerAuth: []
        responses:
          200:
            description: Allowed methods returned
        """

        return handle_options_request(resource_class=self)


class OperatorPostResource(Resource):
    """
    Resource for creating new operators.
    This class provides a method to create a new operator record in the database.
    """

    ENDPOINT_PATHS = [f"/{BP_NAME}"]

    @jwt_required()
    def post(self, identity) -> Response:
        """
        ---
        tags:
        - API Server (api_server)
        summary: Create a new operator
        description: Create a new operator record in the database.
        operationId: createOperator
        security:
        - bearerAuth: []
        requestBody:
        required: true
        content:
                application/json:
                schema:
                        type: object
                        properties:
                        CF:
                                type: string
                                example: RSSMRA80A01F205X
                        nome:
                                type: string
                                example: Mario
                        cognome:
                                type: string
                                example: Rossi
        responses:
          201:
                  description: Operator created
                  content:
                  application/json:
                          schema:
                          type: object
                          properties:
                                  outcome:
                                  type: string
                                  example: operator successfully created
                                  location:
                                  type: string
                                  example: https://localhost:5000/api/v1/operator/RSSMRA80A01F205X
          400:
                  description: Invalid input
        """

        try:
            # Validate and deserialize input
            data = operator_schema.load(request.get_json())
        except ValidationError as err:
            return create_response(
                message={"error": err.messages},
                status_code=STATUS_CODES["bad_request"],
            )

        cf = data["CF"]
        name = data["nome"]
        surname = data["cognome"]

        # Check if the operator already exists
        operator_exists: Operator = Operator.query.filter_by(CF=cf).first()
        if operator_exists:
            return create_response(
                message={"error": "operator already exists."},
                status_code=STATUS_CODES["bad_request"],
            )

        # Create a new operator instance
        new_operator = Operator(CF=cf, nome=name, cognome=surname)

        # Add the new operator to the database
        db.session.add(new_operator)

        # Commit the changes to the database
        db.session.commit()

        # Log the action
        log(
            message=f"User {identity} created operator with id {new_operator.id}",
            level="INFO",
            message_id="OPRPOST",
            sd_tags={
                "endpoint": request.path,
                "method": request.method,
                "identity": identity,
                "operator_id": new_operator.id,
            },
        )

        # Return the new operator as a JSON response
        return create_response(
            message={
                "outcome": "operator successfully created",
                "location": get_hateos_location_string(
                    bp_name=BP_NAME, id_=new_operator.id
                ),
            },
            status_code=STATUS_CODES["created"],
        )

    @jwt_required()
    def options(self) -> Response:
        """
        ---
        tags:
        - API Server (api_server)
        summary: Get allowed HTTP methods for operator resource
        description: Returns the allowed HTTP methods for the operator resource endpoint.
        operationId: optionsOperatorPost
        security:
        - bearerAuth: []
        responses:
          200:
                  description: Allowed methods returned
        """
        return handle_options_request(resource_class=self)


# Register the blueprint with the API
api.add_resource(OperatorResource, *OperatorResource.ENDPOINT_PATHS)
api.add_resource(OperatorPostResource, *OperatorPostResource.ENDPOINT_PATHS)
