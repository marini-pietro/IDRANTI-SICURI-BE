"""
UserResource blueprint for managing user-related operations.
This module defines the UserResource class, which handles CRUD operations
for user entities in the database.
"""

# Library imports
from base64 import urlsafe_b64encode as base64_urlsafe_b64encode
from re import search as re_search
from re import IGNORECASE as re_IGNORECASE
from os import urandom as os_urandom
from os.path import basename as os_path_basename
from typing import List, Dict, Any, Union
from flask import Blueprint, request, Response
from flask_restful import Api, Resource
from flask_jwt_extended import jwt_required
from requests import post as requests_post
from requests.exceptions import RequestException
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from marshmallow import fields, ValidationError

# Local imports
from configs.api_config import (
    AUTH_SERVER_HOST,
    AUTH_SERVER_PORT,
    PBKDF2HMAC_SETTINGS,
    STATUS_CODES,
    LOGIN_AVAILABLE_THROUGH_API,
    IS_AUTH_SERVER_SSL,
    AUTH_API_VERSION,
)
from api_server import ma, limiter, get_rate_limit

# Import User model for ORM
from models import db, User
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
user_bp = Blueprint(BP_NAME, __name__)
api = Api(user_bp)


# Define schemas and validation function
def safe_string(value: str):
    """
    Custom validation function to ensure that a string does
    not contain potentially dangerous characters.
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


class UserSchema(ma.Schema):
    """
    Schema for validating the contents and structure ofuser data.
    """

    email = fields.Email(required=True)
    comune = fields.String(required=True)
    nome = fields.String(required=True, validate=safe_string)
    cognome = fields.String(required=True, validate=safe_string)
    admin = fields.Boolean(required=True)
    password = fields.String(required=True)


# Create an instance of the schema
user_schema = UserSchema()


def hash_password(password: str) -> str:
    """
    Hashes the string passed as a parameter using PBKDF2HMAC
    with the settings defined with the configuration variables.
    """

    # Generate a random salt
    salt = os_urandom(16)

    # Use PBKDF2 to hash the password
    kdf = PBKDF2HMAC(
        algorithm=PBKDF2HMAC_SETTINGS["algorithm"],
        length=PBKDF2HMAC_SETTINGS["length"],
        salt=salt,
        iterations=PBKDF2HMAC_SETTINGS["iterations"],
        backend=PBKDF2HMAC_SETTINGS["backend"],
    )
    # Derive the hashed password
    hashed_password = base64_urlsafe_b64encode(kdf.derive(password.encode("utf-8")))

    # Store the salt and hashed password together as "salt:hash"
    return f"{base64_urlsafe_b64encode(salt).decode('utf-8')}:{hashed_password.decode('utf-8')}"


class UserResource(Resource):
    """
    UserResource for managing user-related CRUD operations.
    """

    ENDPOINT_PATHS = [f"/{BP_NAME}/<string:email>"]

    @jwt_required()
    @limiter.limit(lambda: get_rate_limit("default"))
    def get(self, email, identity) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Get user by email
        description: Retrieve user information from the database by email.
        operationId: getUserByEmail
        security:
          - bearerAuth: []
        parameters:
          - name: email
            in: path
            required: true
            description: The unique email address of the user to retrieve.
            schema:
              type: string
              example: user@example.com
        responses:
          200:
            description: User found
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    email:
                      type: string
                      example: user@example.com
                    comune:
                      type: string
                      example: Milano
                    nome:
                      type: string
                      example: Mario
                    cognome:
                      type: string
                      example: Rossi
                    admin:
                      type: boolean
                      example: false
          404:
            description: User not found
        """

        # Fetch user data from the database
        user = User.query.filter_by(email=email).first()

        # Check if user exists
        if user is None:
            return create_response(
                message={"error": "user not found"},
                status_code=STATUS_CODES["not_found"],
            )

        # Log the retrieval
        log(
            message=f"User {identity} fetched user {email} data",
            level="INFO",
            message_id="USRGET",
            sd_tags={
                "endpoint": request.path,
                "method": request.method,
                "requester": identity,
                "target_user": email,
            },
        )

        # Return user data as JSON response
        return create_response(
            message={
                "email": user.email,
                "comune": user.comune,
                "nome": user.nome,
                "cognome": user.cognome,
                "admin": user.admin,
            },
            status_code=STATUS_CODES["ok"],
        )

    @jwt_required()
    @limiter.limit(lambda: get_rate_limit("default"))
    def patch(self, email, identity) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Update user by email
        description: Update user information in the database by email. Allows partial updates.
        operationId: updateUserByEmail
        security:
          - bearerAuth: []
        parameters:
          - name: email
            in: path
            required: true
            description: The unique email address of the user to update.
            schema:
              type: string
              example: user@example.com
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  comune:
                    type: string
                    example: Milano
                  nome:
                    type: string
                    example: Mario
                  cognome:
                    type: string
                    example: Rossi
                  admin:
                    type: boolean
                    example: false
                  password:
                    type: string
                    example: newpassword
        responses:
          200:
            description: User updated
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    success:
                      type: string
                      example: User user@example.com updated
          400:
            description: Invalid input
          404:
            description: User not found
        """

        # Load input data
        try:
            data = user_schema.load(
                request.get_json(), partial=True
            )  # partial=True to allow partial updates
        except ValidationError as err:
            return create_response(
                message={"error": err.messages},
                status_code=STATUS_CODES["bad_request"],
            )

        # Check if the user exists in the database using ORM
        user = User.query.filter_by(email=email).first()
        if not user:  # If user is not found return an error message
            return create_response(
                message={"error": "user not found"},
                status_code=STATUS_CODES["not_found"],
            )

        # Update fields if provided
        if "password" in data and data["password"]:
            user.password = hash_password(data["password"])
        if "comune" in data and data["comune"]:
            user.comune = data["comune"]
        if "nome" in data and data["nome"]:
            user.nome = data["nome"]
        if "cognome" in data and data["cognome"]:
            user.cognome = data["cognome"]
        if "admin" in data:
            user.admin = data["admin"]

        # Commit changes to the database
        db.session.commit()

        # Log the update
        log(
            message=f"User {identity} updated user {email}",
            level="INFO",
            message_id="USRPATCH",
            sd_tags={
                "endpoint": request.path,
                "method": request.method,
                "updater": identity,
                "updated_user": email,
            },
        )

        # Return a success response
        return create_response(
            message={"success": f"User {email} updated"},
            status_code=STATUS_CODES["ok"],
        )

    @jwt_required()
    @limiter.limit(lambda: get_rate_limit("default"))
    def delete(self, email, identity) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Delete user by email
        description: Delete a user from the database by email.
        operationId: deleteUserByEmail
        security:
          - bearerAuth: []
        parameters:
          - name: email
            in: path
            required: true
            description: The unique email address of the user to delete.
            schema:
              type: string
              example: user@example.com
        responses:
          200:
            description: User deleted
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    success:
                      type: string
                      example: User user@example.com deleted
          404:
            description: User not found
        """

        user = User.query.filter_by(
            email=email
        ).first()  # Check if the user exists in the database

        if user is None:  # If user is not found return an error message
            return create_response(
                message={"error": "user not found with provided email"},
                status_code=STATUS_CODES["not_found"],
            )

        # Execute the delete query
        db.session.delete(user)

        # Commit the changes to the database
        db.session.commit()

        # Log the deletion
        log(
            message=f"User {email} deleted user {identity}",
            level="INFO",
            message_id="USRDEL",
            sd_tags={
                "endpoint": request.path,
                "method": request.method,
                "deleter": email,
                "deleted_user": identity,
            },
        )

        # Return a success response
        return create_response(
            message={"success": f"User {email} deleted"},
            status_code=STATUS_CODES["ok"],
        )

    @jwt_required()
    def options(self) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Get allowed HTTP methods for user resource
        description: Returns the allowed HTTP methods for the user resource endpoint.
        operationId: optionsUser
        security:
          - bearerAuth: []
        responses:
          200:
            description: Allowed methods returned
        """
        return handle_options_request(resource_class=self)


class UserPostResource(Resource):
    """
    UserResource post resource for creating new users.
    This class handles the following HTTP methods:
    - POST: Create a new user
    - OPTIONS: Get allowed HTTP methods for this endpoint
    """

    ENDPOINT_PATHS = [f"/{BP_NAME}"]

    @jwt_required()
    @limiter.limit(lambda: get_rate_limit("default"))
    def post(self, identity) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Create a new user
        description: Create a new user in the database.
        operationId: createUser
        security:
          - bearerAuth: []
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  email:
                    type: string
                    example: user@example.com
                  password:
                    type: string
                    example: mypassword
                  comune:
                    type: string
                    example: Milano
                  nome:
                    type: string
                    example: Mario
                  cognome:
                    type: string
                    example: Rossi
                  admin:
                    type: boolean
                    example: false
        responses:
          201:
            description: User created
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    outcome:
                      type: string
                      example: User user@example.com created
                    location:
                      type: string
                      example: https://localhost:5000/api/v1/user/user@example.com
          400:
            description: Invalid input
          409:
            description: User already exists
        """

        # Load input data
        try:
            data = user_schema.load(request.get_json())
        except ValidationError as err:
            return create_response(
                message={"error": err.messages},
                status_code=STATUS_CODES["bad_request"],
            )

        email: str = data["email"]
        password: str = data["password"]
        comune: str = data["comune"]
        nome: str = data["nome"]
        cognome: str = data["cognome"]
        admin: str = data.get("admin", False)  # Default to False if not provided

        # Check if the user already exists in the database using EXISTS keyword
        user_exists: bool = User.query.filter_by(email=email).count() > 0
        if user_exists:
            return create_response(
                message={"error": "user with provided email already exists"},
                status_code=STATUS_CODES["conflict"],
            )

        # Hash the password
        hashed_password: str = hash_password(password)

        # Insert the new user into the database
        new_user = User(
            email=email,
            password=hashed_password,
            comune=comune,
            nome=nome,
            cognome=cognome,
            admin=admin,
        )

        # Add the new user to the database
        db.session.add(new_user)

        # Commit the changes to the database
        db.session.commit()

        # Log the creation
        log(
            message=f"User {identity} created user {email}",
            level="INFO",
            message_id="USRPOST",
            sd_tags={
                "endpoint": request.path,
                "method": request.method,
                "identity": identity,
                "email": email,
            },
        )

        # Return a success response
        return create_response(
            message={
                "outcome": f"User {email} created",
                "location": get_hateos_location_string(bp_name=BP_NAME, id_=email),
            },
            status_code=STATUS_CODES["created"],
        )

    @jwt_required()
    def options(self) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Get allowed HTTP methods for user resource
        description: Returns the allowed HTTP methods for the user resource endpoint.
        operationId: optionsUserPost
        security:
          - bearerAuth: []
        responses:
          200:
            description: Allowed methods returned
        """
        return handle_options_request(resource_class=self)


class UserLoginSchema(ma.Schema):
    """
    Schema for validating user login data.
    """

    email = fields.Email(required=True)
    password = fields.String(required=True)


# Create an instance of the schema
user_login_schema = UserLoginSchema()


class UserLogin(Resource):
    """
    UserResource login resource for managing user authentication.
    This class handles the following HTTP methods:
    - POST: UserResource login
    - OPTIONS: Get allowed HTTP methods for this endpoint
    """

    ENDPOINT_PATHS = [f"/{BP_NAME}/auth/login"]

    @limiter.limit(lambda: get_rate_limit("strict"))
    def post(self) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: User login
        description: Authenticate a user and return a JWT token.
        operationId: userLogin
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  email:
                    type: string
                    example: user@example.com
                  password:
                    type: string
                    example: mypassword
        responses:
          200:
            description: Login successful
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    access_token:
                      type: string
                      example: eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
                    refresh_token:
                      type: string
                      example: eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
          400:
            description: Invalid input
          401:
            description: Invalid credentials
          403:
            description: Login not available through API server
          500:
            description: Authentication service unavailable or internal error
        """

        # Check if login is available through the API server
        if not LOGIN_AVAILABLE_THROUGH_API:
            return create_response(
                message={
                    "error": "login not available through API server, "
                    "contact authentication service directly"
                },
                status_code=STATUS_CODES["forbidden"],
            )

        # Validate and deserialize input using Marshmallow
        try:
            data = user_login_schema.load(request.get_json())
        except ValidationError as err:
            return create_response(
                message={"errors": err.messages},
                status_code=STATUS_CODES["bad_request"],
            )

        email: str = data["email"]
        password: str = data["password"]

        try:
            # Forward login request to the authentication service
            scheme = "https" if IS_AUTH_SERVER_SSL else "http"
            auth_login_url: str = (
                f"{scheme}://{AUTH_SERVER_HOST}:{AUTH_SERVER_PORT}/auth/{AUTH_API_VERSION}/login"
            )
            response = requests_post(
                auth_login_url,
                json={"email": email, "password": password},
                timeout=5,
            )
        except RequestException as ex:

            # Log the error
            log(
                message=f"Authentication service unavailable: {str(ex)}",
                level="ERROR",
                message_id="AUTHSRVUNAVAIL",
                sd_tags={"endpoint": request.path, "method": request.method},
            )

            # Return error response
            return create_response(
                message={"error": "authentication service unavailable"},
                status_code=STATUS_CODES["internal_server_error"],
            )

        # Handle response from the authentication service
        if response.status_code == STATUS_CODES["ok"]:
            # If the login is successful, send the token back to the user
            # Logging login is already handled by auth server so just return the response
            return create_response(
                message=response.json(), status_code=STATUS_CODES["ok"]
            )

        if response.status_code == STATUS_CODES["unauthorized"]:  # Invalid credentials
            # Log the failed login attempt
            log(
                message=f"Failed login attempt for email: {email}",
                level="WARNING",
                message_id="LOGINFAIL",
                sd_tags={
                    "endpoint": request.path,
                    "method": request.method,
                    "email": email,
                },
            )

            # Return unauthorized response
            return create_response(
                message={"error": "Invalid credentials"},
                status_code=STATUS_CODES["unauthorized"],
            )

        if response.status_code == STATUS_CODES["bad_request"]:  # Bad request
            # Log the bad request
            log(
                message=f"Bad request during login for email: {email}",
                level="ERROR",
                message_id="LOGINBADREQ",
                sd_tags={
                    "endpoint": request.path,
                    "method": request.method,
                    "email": email,
                },
            )

            # Return bad request response
            return create_response(
                message={"error": "Bad request"},
                status_code=STATUS_CODES["bad_request"],
            )

        if (
            response.status_code == STATUS_CODES["internal_server_error"]
        ):  # Internal server error
            # Log the internal error
            log(
                message=f"Internal error during login for email: {email}",
                level="ERROR",
                message_id="LOGINERR",
                sd_tags={
                    "endpoint": request.path,
                    "method": request.method,
                    "email": email,
                },
            )

            # Return internal error response
            return create_response(
                message={"error": "Internal error"},
                status_code=STATUS_CODES["internal_server_error"],
            )

        else:
            # Log any unexpected errors
            log(
                message=f"Unexpected error during login for email: {email} "
                f"with status code: {response.status_code}",
                level="ERROR",
                message_id="LOGINERR",
                sd_tags={
                    "endpoint": request.path,
                    "method": request.method,
                    "email": email,
                    "status_code": response.status_code,
                },
            )

            # Return generic internal error response
            return create_response(
                message={"error": "Unexpected error during login"},
                status_code=STATUS_CODES["internal_server_error"],
            )

    def options(self) -> Response:
        """
        ---
        tags:
          - API Server (api_server)
        summary: Get allowed HTTP methods for user login resource
        description: Returns the allowed HTTP methods for the user login endpoint.
        responses:
          200:
            description: Allowed methods returned
        """
        return handle_options_request(resource_class=self)


# Register the resources with the API
api.add_resource(UserResource, *UserResource.ENDPOINT_PATHS)
api.add_resource(UserPostResource, *UserPostResource.ENDPOINT_PATHS)
api.add_resource(UserLogin, *UserLogin.ENDPOINT_PATHS)
