"""
Blueprint for managing hydrant photos.
This module provides endpoints to create, read, update, and delete photos associated with hydrants.
"""

# Library imports
from os.path import basename as os_path_basename
from typing import List
from re import search as re_search
from re import IGNORECASE as re_IGNORECASE
from flask import Blueprint, request, Response
from flask_restful import Api, Resource
from flask_jwt_extended import jwt_required
from marshmallow import fields, ValidationError, validate
from sqlalchemy import exists

# Local imports
from models import db, Photo, Hydrant
from api_server import ma, limiter, get_rate_limit
from api_config import (
    STATUS_CODES,
)
from .blueprints_utils import (
    check_authorization,
    log,
    create_response,
    handle_options_request,
    get_hateos_location_string,
)

# Define constants
BP_NAME = os_path_basename(__file__).replace("_bp.py", "")

# Create the blueprint and API
photo_bp = Blueprint(BP_NAME, __name__)
api = Api(photo_bp)


# Marshmallow Schemas
def safe_string(value: str):
    """
    Custom validation function to ensure that a string does not
    contain potentially dangerous characters.
    Checks for the presence of "<", ">", "javascript:" and control characters.
    If the string contains any of these, a ValidationError is raised.
    This helps to prevent injection attacks and XSS vulnerabilities.
    If the string is valid, it is returned unchanged.

    @param value: The string value to validate.
    @return: The original string if it is valid.
    @raises ValidationError: If the string contains invalid characters.
    """

    if not isinstance(value, str):
        raise ValidationError("Must be a string.")
    # Reject <, >, javascript:, and control chars
    if (
        "<" in value
        or ">" in value
        or re_search(r"javascript:|[\x00-\x1F\x7F]", value, re_IGNORECASE)
    ):
        raise ValidationError("Invalid characters in string.")
    return value


class PhotoSchema(ma.Schema):
    """
    Schema for validating and serializing photo data.
    This schema defines the fields required for a photo associated with a hydrant.
    """

    id_idrante = fields.Integer(required=True, validate=validate.Range(min=1))
    posizione = fields.String(required=True, validate=safe_string)
    data = fields.Date(required=True)


# Create the schema instance
photo_schema = PhotoSchema()


class PhotoResource(Resource):
    """
    Photo resource for managing hydrant photos.
    This class provides methods to create, read, update, and delete photos associated with hydrants.
    """

    ENDPOINT_PATHS = [f"/{BP_NAME}/<int:id_>"]

    @jwt_required()
    @limiter.limit(lambda: get_rate_limit("default"))
    def get(self, hydrant_id, identity) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Get photos by hydrant ID
        description: Retrieve all photos associated with a hydrant by its integer ID.
        operationId: getPhotosByHydrantId
        security:
          - bearerAuth: []
        parameters:
          - name: hydrant_id
            in: path
            required: true
            schema:
              type: integer
              example: 1
        responses:
          200:
            description: Photos found
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      posizione:
                        type: string
                        example: "foto/1.png"
                      data:
                        type: string
                        format: date
                        example: "2024-05-01"
          400:
            description: Invalid hydrant ID
          404:
            description: Hydrant or photos not found
        """

        # Validate the hydrant_id
        if hydrant_id < 0:
            return create_response(
                message={"error": "hydrant id_ must be positive integer"},
                status_code=STATUS_CODES["bad_request"],
            )

        # Check that hydrant exists
        hydrant = Photo.query.filter_by(id=hydrant_id).first()
        if hydrant is None:
            return create_response(
                message={"error": "specified hydrant not found"},
                status_code=STATUS_CODES["not_found"],
            )

        # Get the data
        photos: List[Photo] = (
            Photo.query.filter_by(id_idrante=hydrant_id)
            .with_entities(Photo.posizione, Photo.data)
            .all()
        )

        # Check if photos exist
        if not photos:
            return create_response(
                message={"error": "no photos found"},
                status_code=STATUS_CODES["not_found"],
            )

        # Log the action
        log(
            message=f"User {identity} fetched photos with hydrant id {hydrant_id}",
            level="INFO",
            message_id="PHOGET",
            sd_tags={
                "endpoint": request.path,
                "method": request.method,
                "identity": identity,
                "hydrant_id": hydrant_id,
            },
        )

        # Return the photos as a JSON response
        return create_response(
            message=[photo.to_dict() for photo in photos],
            status_code=STATUS_CODES["ok"],
        )

    @jwt_required()
    @limiter.limit(lambda: get_rate_limit("default"))
    def patch(self, id_, identity) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Update a photo by ID
        description: Update an existing photo record by its integer ID. Allows partial updates.
        operationId: updatePhotoById
        security:
          - bearerAuth: []
        parameters:
          - name: id_
            in: path
            required: true
            description: The unique identifier of the photo to update.
            schema:
              type: integer
              example: 1
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  id_idrante:
                    type: integer
                    example: 1
                  posizione:
                    type: string
                    example: "foto/1.png"
                  data:
                    type: string
                    format: date
                    example: "2024-05-01"
              example:
                id_idrante: 1
                posizione: "foto/1.png"
                data: "2024-05-01"
        responses:
          200:
            description: Photo updated
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    outcome:
                      type: string
                      example: photo successfully updated
                    location:
                      type: string
                      example: /photo/1
                example:
                  outcome: photo successfully updated
          400:
            description: Invalid input
          404:
            description: Photo not found
        """

        # Validate the ID
        if id_ <= 0:
            return create_response(
                message={"error": "photo id_ must be positive integer"},
                status_code=STATUS_CODES["bad_request"],
            )

        photo = Photo.query.get(id_)  # Retrieve the photo by ID
        if photo is None:  # If a photo with specified ID is not found
            return create_response(
                message={"error": "photo with specified id not found"},
                status_code=STATUS_CODES["not_found"],
            )

        # Validate and deserialize input data
        try:
            # Allow partial updates
            data = photo_schema.load(request.get_json(), partial=True)
        except ValidationError as err:
            return create_response(
                message={"error": err.messages},
                status_code=STATUS_CODES["bad_request"],
            )

        # Update the photo fields
        for key, value in data.items():
            setattr(photo, key, value)

        # Commit the changes to the database
        db.session.commit()

        # Log the action
        log(
            message=f"User {identity} updated photo with id_ {id_}",
            level="INFO",
            message_id="PHOPATCH",
            sd_tags={
                "endpoint": request.path,
                "method": request.method,
                "identity": identity,
                "photo_id": id_,
            },
        )

        # Return the response
        return create_response(
            message={
                "outcome": "photo successfully updated",
                "location": get_hateos_location_string(bp_name=BP_NAME, id_=id_),
            },
            status_code=STATUS_CODES["ok"],
        )

    @jwt_required()
    @limiter.limit(lambda: get_rate_limit("default"))
    def delete(self, id_, identity) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Delete a photo by ID
        description: Delete a photo record from the database by its integer ID.
        operationId: deletePhotoById
        security:
          - bearerAuth: []
        parameters:
          - name: id_
            in: path
            required: true
            schema:
              type: integer
              example: 1
        responses:
          200:
            description: Photo deleted
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    outcome:
                      type: string
                      example: photo successfully deleted
          400:
            description: Invalid ID
          404:
            description: Photo not found
        """

        # Validate the ID
        if id_ <= 0:
            return create_response(
                message={"error": "photo id_ must be positive integer"},
                status_code=STATUS_CODES["bad_request"],
            )

        photo = Photo.query.get(id_)  # Retrieve the photo by ID
        if photo is None:  # If a photo with specified ID is not found
            return create_response(
                message={"error": "photo with specified id not found"},
                status_code=STATUS_CODES["not_found"],
            )

        # Delete the photo
        db.session.delete(photo)

        # Commit the changes to the database
        db.session.commit()

        # Log the action
        log(
            message=f"User {identity} deleted photo with id_ {id_}",
            level="INFO",
            message_id="PHODEL",
            sd_tags={
                "endpoint": request.path,
                "method": request.method,
                "identity": identity,
                "photo_id": id_,
            },
        )

        # Return the response
        return create_response(
            message={"outcome": "photo successfully deleted"},
            status_code=STATUS_CODES["ok"],
        )

    @jwt_required()
    def options(self) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Get allowed HTTP methods for photo resource
        description: Returns the allowed HTTP methods for the photo resource endpoint.
        operationId: optionsPhoto
        security:
          - bearerAuth: []
        responses:
          200:
            description: Allowed methods returned
        """

        return handle_options_request(resource_class=self)


class PhotoPostResource(Resource):
    """
    Resource for creating new photos associated with hydrants.
    This class provides a method to create a new photo record.
    """

    ENDPOINT_PATHS = [f"/{BP_NAME}"]

    @jwt_required()
    @limiter.limit(lambda: get_rate_limit("default"))
    def post(self, identity) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Create a new photo
        description: Create a new photo record associated with a hydrant.
        operationId: createPhoto
        security:
          - bearerAuth: []
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  id_idrante:
                    type: integer
                    example: 1
                  posizione:
                    type: string
                    example: "foto/1.png"
                  data:
                    type: string
                    format: date
                    example: "2024-05-01"
        responses:
          201:
            description: Photo created
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    outcome:
                      type: string
                      example: photo successfully created
                    location:
                      type: string
                      example: https://localhost:5000/api/v1/photo/1
          400:
            description: Invalid input
          404:
            description: Hydrant not found
        """

        # Validate and deserialize input data
        try:
            data = photo_schema.load(request.get_json())
        except ValidationError as err:
            return create_response(
                message={"error": err.messages},
                status_code=STATUS_CODES["bad_request"],
            )

        hydrant_id = data["id_idrante"]
        position = data["posizione"]
        date = data["data"]

        # Optimized check that related hydrant exists
        hydrant_exists: bool = db.session.query(
            exists().where(Hydrant.id == hydrant_id)
        ).scalar()
        if not hydrant_exists:
            return create_response(
                message={"error": "hydrant not found"},
                status_code=STATUS_CODES["not_found"],
            )

        # Check if the photo already exists
        photo_exists: bool = (
            Photo.query.filter_by(
                id_idrante=hydrant_id, posizione=position, data=date
            ).first()
            is not None
        )
        if photo_exists:
            return create_response(
                message={"error": "photo already exists."},
                status_code=STATUS_CODES["bad_request"],
            )

        # Create a new photo instance
        new_photo = Photo(id_idrante=hydrant_id, posizione=position, data=date)

        # Insert the new photo into the database
        db.session.add(new_photo)

        # Commit the changes to the database
        db.session.commit()

        # Log the action
        log(
            message=f"User {identity} created photo with hydrant id_ {hydrant_id}",
            level="INFO",
            message_id="PHOPOST",
            sd_tags={
                "endpoint": request.path,
                "method": request.method,
                "identity": identity,
                "hydrant_id": hydrant_id,
            },
        )

        # Return the response
        return create_response(
            message={
                "outcome": "photo successfully created",
                "location": get_hateos_location_string(
                    bp_name=BP_NAME, id_=new_photo.id_foto
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
        summary: Get allowed HTTP methods for photo resource
        description: Returns the allowed HTTP methods for the photo resource endpoint.
        operationId: optionsPhotoPost
        security:
          - bearerAuth: []
        responses:
          200:
            description: Allowed methods returned
        """

        return handle_options_request(resource_class=self)


# Register the resources with the API
api.add_resource(PhotoResource, *PhotoResource.ENDPOINT_PATHS)
api.add_resource(PhotoPostResource, *PhotoPostResource.ENDPOINT_PATHS)
