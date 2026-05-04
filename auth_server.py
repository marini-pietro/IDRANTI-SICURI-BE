"""
Authentication server for user login and JWT token generation.
This server provides endpoints for user authentication, token validation, and health checks.
"""

# Library imports
from base64 import urlsafe_b64decode
from binascii import Error as BinasciiError
from typing import Dict, Union, List, Any
from subprocess import run as subprocess_run
from datetime import datetime as datetime_obj
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.exceptions import InvalidKey
from flask import Flask, request, jsonify
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
    get_jwt,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Local imports
from logging_interface import create_interface
from models import db, User
from auth_config import (
    AUTH_SERVER_HOST,
    AUTH_SERVER_PORT,
    AUTH_API_VERSION,
    AUTH_SERVER_IDENTIFIER,
    AUTH_SERVER_DEBUG_MODE,
    AUTH_SERVER_SSL_CERT,
    AUTH_SERVER_SSL_KEY,
    AUTH_SERVER_SSL,
    AUTH_SERVER_RATE_LIMIT,
    PBKDF2HMAC_SETTINGS,
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    JWT_QUERY_STRING_NAME,
    JWT_JSON_KEY,
    JWT_REFRESH_JSON_KEY,
    JWT_TOKEN_LOCATION,
    JWT_ACCESS_TOKEN_EXPIRES,
    STATUS_CODES,
    JWT_REFRESH_TOKEN_EXPIRES,
    SQL_PATTERN,
    SQLALCHEMY_DATABASE_URI,
    SQLALCHEMY_TRACK_MODIFICATIONS,
    RATE_LIMIT_TIERS,
    LOG_SERVER_HOST,
    LOG_SERVER_PORT,
    # To lessen verbosity, the prefix "AUTH_SERVER_"
    # is not used for the following logging interface settings,
    # but, being taken from the auth_config module, they are already properly namespaced.
    LOG_INTERFACE_DB_FILENAME,
    LOG_INTERFACE_MAX_RETRIES,
    LOG_INTERFACE_BATCH_DELAY,
)

# Initialize Flask app
auth_api = Flask(__name__)

# Update configuration settings for the Flask app
auth_api.config.update(
    JWT_SECRET_KEY=JWT_SECRET_KEY,  # Same secret key as the auth microservice
    JWT_ALGORITHM=JWT_ALGORITHM,  # Same algorithm as the auth microservice
    JWT_TOKEN_LOCATION=JWT_TOKEN_LOCATION,  # Where to look for tokens
    JWT_QUERY_STRING_NAME=JWT_QUERY_STRING_NAME,  # Custom query string name
    JWT_JSON_KEY=JWT_JSON_KEY,  # Custom JSON key for access tokens
    JWT_REFRESH_JSON_KEY=JWT_REFRESH_JSON_KEY,  # Custom JSON key for refresh tokens
    JWT_REFRESH_TOKEN_EXPIRES=JWT_REFRESH_TOKEN_EXPIRES,  # Refresh token valid duration
    JWT_ACCESS_TOKEN_EXPIRES=JWT_ACCESS_TOKEN_EXPIRES,  # Access token valid duration
    SQLALCHEMY_DATABASE_URI=SQLALCHEMY_DATABASE_URI,  # Database connection URI
    SQLALCHEMY_TRACK_MODIFICATIONS=SQLALCHEMY_TRACK_MODIFICATIONS,  # Disable track modifications
)

# Initialize database (ORM abstraction layer)
db.init_app(auth_api)

# Initialize JWT manager
jwt = JWTManager(auth_api)


# Helper function to get rate limit string for a specific tier
def get_rate_limit(tier: str = "default") -> str:
    """
    Get rate limit string for a specific tier.

    Flask-Limiter expects human-readable granularities (e.g. "per second").
    This helper returns strings in the form "<max> per <window> second(s)".
    """

    tier_config = RATE_LIMIT_TIERS.get(tier, RATE_LIMIT_TIERS["default"])
    max_requests = tier_config["max"]
    window = tier_config["window"]
    if window == 1:
        return f"{max_requests} per second"
    return f"{max_requests} per {window} seconds"


# Initialize Rate Limiter (flask-limiter)
limiter = Limiter(
    app=auth_api,
    key_func=get_remote_address,
    default_limits=[get_rate_limit("default")],
    storage_uri="memory://",
    enabled=True if AUTH_SERVER_RATE_LIMIT == True else False,
)

# Initialize logging interface
# Using factory function from logging_interface module
log_interface = create_interface(
    syslog_host=LOG_SERVER_HOST,
    syslog_port=LOG_SERVER_PORT,
    db_filename=LOG_INTERFACE_DB_FILENAME,
    service_name=AUTH_SERVER_IDENTIFIER,
    max_retries=LOG_INTERFACE_MAX_RETRIES,
    retry_delay=LOG_INTERFACE_BATCH_DELAY,
)

print("Logging interface created successfully. Starting background thread...")
log_interface.start()  # Start the background thread for the logging interface
print("Logging interface background thread started successfully.")

log = (
    log_interface.log
)  # Effectively rename the log method from the interface for better readability in the code

# Check JWT secret key length
# encode to utf-8 to get byte length and check if it's at least 32 bytes (256 bits)
if len(JWT_SECRET_KEY.encode("utf-8")) < 32:
    raise ValueError("jwt secret key too short")


def verify_password(stored_password: str, provided_password: str) -> bool:
    """Verify a password against a stored PBKDF2 hash with more specific exception handling."""

    try:
        # Split the stored password into salt and hash components
        salt_b64, hash_b64 = stored_password.split(":")  # Expecting "salt:hash" format
    except ValueError:
        # stored_password doesn't have the expected "salt:hash" format
        log(
            message="Stored password format invalid",
            level="WARNING",
            message_id="PWDFMTERR",
            sd_tags={"host": AUTH_SERVER_HOST, "port": AUTH_SERVER_PORT},
        )
        return False

    try:
        # Decode the base64-encoded salt and hash
        salt = urlsafe_b64decode(salt_b64)
        hash_bytes = urlsafe_b64decode(hash_b64)
    except (BinasciiError, ValueError):
        # base64 decoding failed (malformed salt or hash)
        log(
            message="Base64 decoding failed for stored password components",
            level="WARNING",
            message_id="PWDDECOERR",
            sd_tags={"host": AUTH_SERVER_HOST, "port": AUTH_SERVER_PORT},
        )
        return False

    try:
        # Set up the PBKDF2 HMAC verifier
        # verifier has to be set up with the same parameters used during hashing
        kdf = PBKDF2HMAC(
            algorithm=PBKDF2HMAC_SETTINGS["algorithm"],
            length=PBKDF2HMAC_SETTINGS["length"],
            salt=salt,
            iterations=PBKDF2HMAC_SETTINGS["iterations"],
        )

        # Verify the provided password
        kdf.verify(provided_password.encode("utf-8"), hash_bytes)

        # If no exception was raised, the password is correct
        return True
    except InvalidKey:
        # password verification failed (wrong password)
        return False
    except Exception as exc:
        # Catch-all for unexpected errors; log for troubleshooting
        log(
            message=f"Unexpected error during password verification: {exc}",
            level="ERROR",
            message_id="PWDVERERR",
            sd_tags={"host": AUTH_SERVER_HOST, "port": AUTH_SERVER_PORT},
        )
        return False


def is_input_safe(data: Union[str, List[str], Dict[Any, Any]]) -> bool:
    """
    Check if the input data (string, list, or dictionary) contains SQL instructions.
    Returns True if safe, False if potentially unsafe.
    """

    # Check for SQL patterns in strings
    if isinstance(data, str):
        return not SQL_PATTERN.search(data)

    # Check for SQL patterns in lists of strings
    if isinstance(data, list):
        return all(
            isinstance(item, str) and not SQL_PATTERN.search(item) for item in data
        )

    # Check for SQL patterns in dictionary keys and values
    if isinstance(data, dict):
        return all(
            isinstance(key, str)
            and isinstance(value, str)
            and not SQL_PATTERN.search(value)
            for key, value in data.items()
        )

    # If data is of an unexpected type, raise TypeError
    raise TypeError(
        "Input must be a string, list of strings, or dictionary with string keys and values."
    )


@auth_api.route(f"/auth/{AUTH_API_VERSION}/login", methods=["POST"])
@limiter.limit(lambda: get_rate_limit("strict"))
def login():
    """
    Login endpoint to authenticate users and generate JWT tokens.
    ---
    tags:
      - Authentication
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
        description: Successful login, returns JWT tokens
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
        description: Bad request (missing or invalid data)
      401:
        description: Invalid credentials
    """

    # Validate request content type and JSON body
    if not request.is_json or request.json is None:
        return (
            jsonify(
                {
                    "error": "Request body must be valid JSON with Content-Type: application/json"
                }
            ),
            STATUS_CODES["bad_request"],
        )

    # Parse and validate JSON body
    try:
        data = request.get_json(
            silent=False
        )  # silent=False to raise error on invalid JSON
        if not data:  # Check for empty JSON object
            return (
                jsonify({"error": "Request body must not be empty"}),
                STATUS_CODES["bad_request"],
            )
    except Exception:
        return jsonify({"error": "Invalid JSON format"}), STATUS_CODES["bad_request"]

    # Validate JSON keys and values for SQL injection
    for key, value in data.items():
        if not is_input_safe(key):
            return (
                jsonify({"error": f"Invalid JSON key: {key} suspected SQL injection"}),
                STATUS_CODES["bad_request"],
            )
        if isinstance(value, str):
            # Separate if statemet for performance reasons
            # (expensive regex will be done only if value is a string)
            if not is_input_safe(value):
                return (
                    jsonify(
                        {
                            "error": f"Invalid JSON value for key '{key}': suspected SQL injection"
                        }
                    ),
                    STATUS_CODES["bad_request"],
                )

    # Extract email and password from JSON body
    email = data.get("email")
    password = data.get("password")
    if not email or not password:  # Check for missing fields
        return (
            jsonify({"error": "Missing email or password"}),
            STATUS_CODES["bad_request"],
        )

    user: User | None = User.query.filter_by(
        email=email
    ).first()  # Fetch user from database
    if user and verify_password(
        user.password, password
    ):  # If the user exists and password is correct
        identity = user.email  # Use email as identity
        additional_claims = {"role": user.ruolo}  # Add user role as custom claim

        # Create access and refresh tokens
        access_token = create_access_token(
            identity=identity, additional_claims=additional_claims
        )
        refresh_token = create_refresh_token(
            identity=identity, additional_claims=additional_claims
        )

        # Logging the successful login event
        log(
            message=f"User {email} logged in",
            level="INFO",
            message_id="LOGIN",
            sd_tags={
                "host": AUTH_SERVER_HOST,
                "port": AUTH_SERVER_PORT,
                "endpoint": request.path,
                "method": request.method,
                "email": email,
            },
        )

        # Return the tokens
        return (
            jsonify({"access_token": access_token, "refresh_token": refresh_token}),
            STATUS_CODES["ok"],
        )
    else:  # Invalid credentials (user not found or wrong password)
        return jsonify({"error": "invalid credentials"}), STATUS_CODES["unauthorized"]


@jwt_required()
@auth_api.route(f"/auth/{AUTH_API_VERSION}/validate", methods=["POST"])
@limiter.limit(lambda: get_rate_limit("strict"))
def validate_token():
    """
    Validate endpoint to check the validity of a JWT token.
    ---
    tags:
      - Authentication
    security:
      - bearerAuth: []
    responses:
      200:
        description: Token is valid
        content:
          application/json:
            schema:
              type: object
              properties:
                identity:
                  type: string
                  example: user@example.com
                role:
                  type: string
                  example: admin
      401:
        description: Invalid or expired token
    """

    # Get identity and custom claims from the JWT
    identity = get_jwt_identity()
    user_role: str | None = get_jwt().get("role")

    return jsonify({"identity": identity, "role": user_role}), STATUS_CODES["ok"]


@auth_api.route(f"/auth/{AUTH_API_VERSION}/refresh", methods=["POST"])
@limiter.limit(lambda: get_rate_limit("strict"))
@jwt_required(refresh=True)
def refresh():
    """
    Refresh endpoint to issue a new access token using a refresh token.
    ---
    tags:
      - Authentication
    security:
      - bearerAuth: []
    responses:
      200:
        description: New access token issued
        content:
          application/json:
            schema:
              type: object
              properties:
                access_token:
                  type: string
                  example: eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
      401:
        description: Invalid or expired refresh token
    """
    # Get the identity from the refresh token
    identity = get_jwt_identity()

    # Preserve custom claims from the refresh token (e.g. role) when issuing a new access token
    user_role: str | None = get_jwt().get("role")
    additional_claims: dict[str, str] | None = (
        {"role": user_role} if user_role is not None else None
    )

    # create_access_token expects additional_claims to be a dict or omitted
    if additional_claims:
        new_access_token = create_access_token(
            identity=identity, additional_claims=additional_claims
        )
    else:
        new_access_token = create_access_token(identity=identity)

    # Logging the token refresh event
    log(
        message=f"Access token refreshed for identity {identity}",
        level="INFO",
        message_id="REFTOK",
        sd_tags={
            "host": AUTH_SERVER_HOST,
            "port": AUTH_SERVER_PORT,
            "endpoint": request.path,
            "method": request.method,
            "identity": identity,
        },
    )

    return jsonify({"access_token": new_access_token}), STATUS_CODES["ok"]


# Endpoint to clear sent logs before a given timestamp
@jwt_required()
@auth_api.route(f"/auth/{AUTH_API_VERSION}/logs/clear", methods=["POST"])
@limiter.limit(lambda: get_rate_limit("strict"))
def clear_sent_logs():
    """
    ---
    tags:
        - AUTH Server (auth_server)
    summary: Clear sent logs before a timestamp
    description: Deletes all logs marked as sent (sent=1) with timestamp before
    the given timestamp (expected in UTC, no timezone indicators, e.g. "2025-07-21 10:30:45").
    operationId: clear_sent_logs
    requestBody:
        required: true
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        timestamp:
                            type: string
                            format: date-time
                            example: "2025-07-21 10:30:45"
                    required:
                        - timestamp
    responses:
        200:
            description: Number of deleted logs
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            deleted:
                                type: integer
        400:
            description: Invalid or missing timestamp
    """
    timestamp_str: str | None = None
    try:
        # Extract and validate admin authorization
        identity = get_jwt_identity()

        # Fetch user from database to check role
        user = User.query.filter_by(email=identity).first()
        if not user or user.ruolo != "admin":
            log(
                message=f"Unauthorized log clear attempt by {identity} (not admin)",
                level="WARNING",
                message_id="CLRLOGSUNAUTH",
                sd_tags={"endpoint": request.path, "identity": identity},
            )
            return (
                jsonify({"error": "Only admins can clear logs"}),
                STATUS_CODES["forbidden"],
            )

        # Parse JSON body and extract timestamp
        data = request.get_json(force=True)
        timestamp_str = data.get("timestamp")

        # Check if timestamp is provided
        if timestamp_str is None:
            return (
                jsonify({"error": "Missing 'timestamp' in request body"}),
                STATUS_CODES["bad_request"],
            )

        # Parse timestamp as naive datetime in UTC (no timezone info expected)
        # If there are any indicators (like timezone info or 'Z'), raise an error
        try:
            before_timestamp: datetime_obj = datetime_obj.fromisoformat(timestamp_str)
        except Exception:
            return (
                jsonify(
                    {
                        "error": "Invalid timestamp format. Use ISO8601 format in UTC "
                        "(e.g. '2025-07-21 10:30:45') without timezone info."
                    }
                ),
                STATUS_CODES["bad_request"],
            )

        # Delete logs marked as sent (sent=1) with timestamp before the given UTC timestamp
        deleted: int = log_interface.clear_sent_logs_before(before_timestamp)

        # Log action with structured data and message ID for observability
        log(
            message=f"Cleared {deleted} sent logs before {before_timestamp} (UTC)",
            level="INFO",
            sd_tags={"timestamp": timestamp_str},
            message_id="CLRLOGS",
        )

        # Return the number of deleted logs in the response
        return jsonify({"Successfully deleted logs": deleted}), STATUS_CODES["ok"]
    except Exception as ex:
        # Log the error with structured data and message ID for observability
        log(
            message=f"Internal server occurred while deleting logs (ex: {ex})",
            level="ERROR",
            sd_tags=(
                {"timestamp_str": timestamp_str} if timestamp_str is not None else None
            ),
            message_id="CLRLOGSERR",
        )
        # Return a generic error message without exposing internal details
        return (
            jsonify(
                {
                    "Internal server error while deleting logs": "No more information given for security purposes, check logs for further detail"
                }
            ),
            STATUS_CODES["internal_server_error"],
        )


@auth_api.route("/health", methods=["GET"])
@limiter.limit(lambda: get_rate_limit("default"))
def health_check():
    """
    Health check endpoint to verify the server is running.
    ---
    tags:
      - Health
    summary: Health check endpoint
    description: Returns a simple status message to indicate the server is healthy.
    operationId: auth_health_check
    responses:
      200:
        description: Server is healthy
        content:
          application/json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  example: ok
    """

    return jsonify({"status": "ok"}), STATUS_CODES["ok"]


if __name__ == "__main__":
    # Run the Flask authentication server

    # Use Flask's built-in server in debug mode for development (i.e. AUTH_SERVER_DEBUG_MODE=True)
    if AUTH_SERVER_DEBUG_MODE is True:
        try:
            # Log server start event
            log(
                message="Auth server starting with Flask built-in server "
                f"with debug mode set to {AUTH_SERVER_DEBUG_MODE}",
                level="INFO",
                message_id="SRVSTART",
                sd_tags={"host": AUTH_SERVER_HOST, "port": AUTH_SERVER_PORT},
            )

            # Start the server with Flask's built-in server
            auth_api.run(
                host=AUTH_SERVER_HOST,
                port=AUTH_SERVER_PORT,
                debug=AUTH_SERVER_DEBUG_MODE,
                ssl_context=(
                    (AUTH_SERVER_SSL_CERT, AUTH_SERVER_SSL_KEY)
                    if AUTH_SERVER_SSL
                    else None
                ),
            )

            # Log server stop event only if run() returns (which is rare, usually only on shutdown)
            log(
                message="Auth server stopped (Flask run() exited)",
                level="INFO",
                message_id="SRVSTOP",
                sd_tags={"host": AUTH_SERVER_HOST, "port": AUTH_SERVER_PORT},
            )
        except Exception as ex:
            log(
                message=f"Exception while starting auth server with Flask: {ex}",
                level="ERROR",
                message_id="SRVSTARTERR",
                sd_tags={"host": AUTH_SERVER_HOST, "port": AUTH_SERVER_PORT},
            )

    # Use waitress-serve in production (i.e. AUTH_SERVER_DEBUG_MODE=False)
    else:
        try:
            # Log server start event
            log(
                message="Auth server starting with waitress-serve",
                level="INFO",
                message_id="SRVSTART",
                sd_tags={"host": AUTH_SERVER_HOST, "port": AUTH_SERVER_PORT},
            )

            # Start the server with waitress-serve
            cmd = [
                "waitress-serve",
                f"--host={AUTH_SERVER_HOST}",
                f"--port={AUTH_SERVER_PORT}",
            ]
            if AUTH_SERVER_SSL:
                cmd.append("--url-scheme=https")
            cmd.append("auth_server:auth_api")

            result = subprocess_run(cmd, capture_output=True, text=True)
            exit_code = result.returncode

            # Log shutdown event
            log(
                message=f"Auth server started with waitress shutdown with code {exit_code}",
                level="INFO",
                message_id="SRVSTOP",
                sd_tags={
                    "host": AUTH_SERVER_HOST,
                    "port": AUTH_SERVER_PORT,
                    "exit_code": exit_code,
                },
            )
        except Exception as ex:
            log(
                message=f"Exception while starting auth server with waitress-serve: {ex}",
                level="ERROR",
                message_id="SRVSTARTERR",
                sd_tags={"host": AUTH_SERVER_HOST, "port": AUTH_SERVER_PORT},
            )
