"""
API server for the application.
This server handles incoming requests and routes them to the appropriate blueprints.
Also provides a health check endpoint.
"""

# Library imports
from typing import Union, List, Dict, Any, Tuple, Optional
from datetime import datetime as datetime_obj
from re import sub as re_sub
from hashlib import sha256 as hashlib_sha256
from hmac import new as hmac_new
from unicodedata import normalize as unicodedata_normalize
from unicodedata import category as unicodedata_category
from sys import exit as sys_exit
from os import listdir as os_listdir
from os.path import join as os_path_join
from os.path import dirname as os_path_dirname
from os.path import abspath as os_path_abspath
from subprocess import run as subprocess_run, PIPE as subprocess_PIPE
from importlib import import_module
from flask import Flask, jsonify, request, Blueprint
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from flask_marshmallow import Marshmallow
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flasgger import Swagger
from sqlalchemy.exc import OperationalError

# Local imports
from api_blueprints.blueprints_utils import log_interface, log
from models import db
from api_config import (
    API_SERVER_HOST,
    API_SERVER_PORT,
    API_SERVER_DEBUG_MODE,
    STATUS_CODES,
    API_VERSION,
    URL_PREFIX,
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    JWT_QUERY_STRING_NAME,
    JWT_JSON_KEY,
    JWT_REFRESH_JSON_KEY,
    JWT_TOKEN_LOCATION,
    JWT_REFRESH_TOKEN_EXPIRES,
    JWT_ACCESS_TOKEN_EXPIRES,
    IS_API_SERVER_SSL,
    API_SERVER_SSL_CERT,
    API_SERVER_SSL_KEY,
    API_SERVER_MAX_JSON_SIZE,
    SQL_SCAN_MAX_LEN,
    SQL_PATTERN,
    SQL_SCAN_MAX_RECURSION_DEPTH,
    SQLALCHEMY_DATABASE_URI,
    SQLALCHEMY_TRACK_MODIFICATIONS,
    SWAGGER_CONFIG,
    INVALID_JWT_MESSAGES,
    RATE_LIMIT_TIERS,
    API_SERVER_RATE_LIMIT,
)

# Create a Flask app
main_api = Flask(__name__)

# Update configuration settings for the Flask app
main_api.config.update(
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

# Swagger template with hardcoded auth endpoints
swagger_template = {
    "openapi": "3.0.2",
    "info": {
        "title": "IDRANTI SICURI API",
        "version": API_VERSION,
        "description": "API documentation for IDRANTI SICURI, including authentication endpoints.",
    },
    "paths": {
        # Only include endpoints data from other services here.
        # Do NOT include API server blueprint endpoints here since they are automatically generated.
        "/auth/login": {
            "post": {
                "tags": ["Authentication (auth_server)"],
                "summary": "Login endpoint to authenticate users and generate JWT tokens.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "email": {
                                        "type": "string",
                                        "example": "user@example.com",
                                    },
                                    "password": {
                                        "type": "string",
                                        "example": "mypassword",
                                    },
                                },
                                "required": ["email", "password"],
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Successful login, returns JWT tokens",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "access_token": {"type": "string"},
                                        "refresh_token": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "400": {"description": "Bad request (missing or invalid data)"},
                    "401": {"description": "Invalid credentials"},
                },
            }
        },
        "/auth/validate": {
            "post": {
                "tags": ["Authentication (auth_server)"],
                "summary": "Validate endpoint to check the validity of a JWT token.",
                "security": [{"bearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "Token is valid",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "identity": {"type": "string"},
                                        "role": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "401": {"description": "Invalid or expired token"},
                },
            }
        },
        "/auth/refresh": {
            "post": {
                "tags": ["Authentication (auth_server)"],
                "summary": "Refresh endpoint to issue a new access token using a refresh token.",
                "security": [{"bearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "New access token issued",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "access_token": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "401": {"description": "Invalid or expired refresh token"},
                },
            }
        },
        "/health": {
            "get": {
                "tags": ["Authentication (auth_server)"],
                "summary": "Health check endpoint to verify the auth server is running.",
                "responses": {
                    "200": {
                        "description": "Server is healthy",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "example": "ok"},
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
    },
    "components": {
        "securitySchemes": {
            "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        }
    },
}

# Configure Flasgger (Swagger UI) with the combined template
main_api.config["SWAGGER"] = {
    "title": "IDRANTI SICURI API Documentation",
    "uiversion": 3,
    "openapi": "3.0.2",
}
# Initialize Swagger
swagger = Swagger(main_api, template=swagger_template, config=SWAGGER_CONFIG)

# Initialize JWTManager for validation only
jwt = JWTManager(main_api)

# Initialize Marshmallow
ma = Marshmallow(main_api)


# Helper function to construct rate limit string for a specific tier
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
    app=main_api,
    key_func=get_remote_address,
    default_limits=[get_rate_limit("default")],
    storage_uri="memory://",
    enabled=True if API_SERVER_RATE_LIMIT == True else False,
)


# Initialize database (ORM abstraction layer)
db.init_app(main_api)

# Standardized error message constants for consistent JSON responses
# f-string formatting is done at the point of response construction with format() function
# so no f prefix needed
ERROR_MESSAGES = {
    "bad_content_type": "Request body must be valid JSON with Content-Type: application/json",
    "empty_body": "Request body must not be empty",
    "invalid_json": "Invalid JSON format",
    "sql_injection_key": "Invalid JSON key: {key} suspected SQL injection",
    "sql_injection_value": "Invalid JSON value for key '{key}': suspected SQL injection",
    "sql_injection_path": "Invalid path variable: {key} suspected SQL injection",
    "payload_too_large": "Request body or field too large",
}


# Helper functions for pre-request checks
def is_input_safe(
    data: Union[str, List[Any], Dict[Any, Any], Tuple[Any]],
    _current_recursion_depth: int = 0,
    _max_recursion_depth: int = SQL_SCAN_MAX_RECURSION_DEPTH,
) -> bool:
    """
    Check if the input data contains SQL instructions.

    Improvements over previous implementation:
    - Treats common scalar types (None, int, float, bool) as safe.
    - Limits recursion depth to avoid excessive work on deeply nested payloads.
    - Limits per-string scan length to the configured `SQL_SCAN_MAX_LEN` to avoid ReDoS.
    - Does not raise TypeError for unknown scalars; instead coerces to str and scans.

    Returns True if safe, False if potentially unsafe.
    """
    # Protect against extremely deep recursion / malicious nesting
    if _current_recursion_depth > _max_recursion_depth:
        # treat overly deep structures as unsafe
        return False

    # None and scalar numeric/bool types are considered safe
    if data is None or isinstance(data, (int, float, bool)):
        return True

    # Strings: check up to SQL_SCAN_MAX_LEN characters to avoid expensive scanning
    if isinstance(data, str):
        try:
            to_scan = data if len(data) <= SQL_SCAN_MAX_LEN else data[:SQL_SCAN_MAX_LEN]
        except Exception:
            # If len() fails for some custom type masquerading as str, coerce and limit
            s = str(data)
            to_scan = s if len(s) <= SQL_SCAN_MAX_LEN else s[:SQL_SCAN_MAX_LEN]
        return not bool(SQL_PATTERN.search(to_scan))

    # Lists/tuples: check each element recursively, increasing depth
    if isinstance(data, (list, tuple)):
        # cheap safety: reject extremely large lists
        if len(data) > 10000:
            return False
        for item in data:
            if not is_input_safe(
                item,
                _current_recursion_depth=_current_recursion_depth + 1,
                _max_recursion_depth=_max_recursion_depth,
            ):
                return False
        return True

    # Dicts: check keys (if strings) and values recursively
    if isinstance(data, dict):
        # cheap safety: reject extremely large dicts
        if len(data) > 10000:
            return False
        for key, value in data.items():
            if isinstance(key, str):
                key_to_scan = (
                    key if len(key) <= SQL_SCAN_MAX_LEN else key[:SQL_SCAN_MAX_LEN]
                )
                if SQL_PATTERN.search(key_to_scan):
                    return False
            # Recurse for the value
            if not is_input_safe(
                value,
                _current_recursion_depth=_current_recursion_depth + 1,
                _max_recursion_depth=_max_recursion_depth,
            ):
                return False
        return True

    # For any other type, coerce to string and scan a limited slice
    try:
        s = str(data)
        to_scan = s if len(s) <= SQL_SCAN_MAX_LEN else s[:SQL_SCAN_MAX_LEN]
        return not bool(SQL_PATTERN.search(to_scan))
    except Exception:
        # If coercion fails, mark as unsafe
        return False


def _check_size_within_limit(
    data: Union[str, List[Any], Dict[Any, Any], Tuple[Any]],
    max_len: int = SQL_SCAN_MAX_LEN,
) -> bool:
    """
    Recursively ensure that no string in the provided data exceeds the configured
    per-field limit.
    Returns True when within limits, False otherwise.
    """

    # check string length
    if isinstance(data, str):
        return len(data) <= max_len

    # check lists/tuples recursively
    if isinstance(data, (list, tuple)):
        for item in data:
            if not _check_size_within_limit(item, max_len=max_len):
                return False
        return True

    # check dicts recursively
    if isinstance(data, dict):
        for key, value in data.items():
            # keys can be non-strings; only check string keys
            if isinstance(key, str) and len(key) > max_len:
                return False
            if not _check_size_within_limit(value, max_len=max_len):
                return False
        return True

    # other types are not size-checked
    return True


def _validate_user_data() -> Optional[Tuple[Any, int]]:
    """
    Helper: validate user data for incoming requests by checking for SQL injection.

    Invoked by `pre_request_checks` handler so the execution order is explicit.

    Returns:
        Optional[Tuple[Any, int]]: Flask response tuple (body, status) when
        validation fails, otherwise None.
    """

    # Validate JSON body for POST, PUT, PATCH methods
    if request.method in ["POST", "PUT", "PATCH"]:
        # Quickly reject requests that declare an excessive Content-Length
        if (
            request.content_length is not None
            and request.content_length > API_SERVER_MAX_JSON_SIZE
        ):
            return (
                jsonify({"error": ERROR_MESSAGES["payload_too_large"]}),
                STATUS_CODES.get("payload_too_large", 413),
            )

        # Ensure Content-Type is application/json and body is valid JSON
        if not request.is_json or request.json is None:
            return (
                jsonify({"error": ERROR_MESSAGES["bad_content_type"]}),
                STATUS_CODES["bad_request"],
            )

        # Parse JSON body
        try:
            data = request.get_json(
                silent=False
            )  # silent=False to raise on invalid JSON
            if data == {}:
                return (
                    jsonify({"error": ERROR_MESSAGES["empty_body"]}),
                    STATUS_CODES["bad_request"],
                )
        except ValueError:
            return (
                jsonify({"error": ERROR_MESSAGES["invalid_json"]}),
                STATUS_CODES["bad_request"],
            )

        # Ensure no individual string field is excessively large (recursive check)
        if not _check_size_within_limit(data):
            return (
                jsonify({"error": ERROR_MESSAGES["payload_too_large"]}),
                STATUS_CODES.get("payload_too_large", 413),
            )

        # Validate JSON keys and values for SQL injection
        for key, value in data.items():
            if not is_input_safe(key):
                return (
                    jsonify(
                        {"error": ERROR_MESSAGES["sql_injection_key"].format(key=key)}
                    ),
                    STATUS_CODES["bad_request"],
                )
            if isinstance(value, str) and not is_input_safe(value):
                return (
                    jsonify(
                        {"error": ERROR_MESSAGES["sql_injection_value"].format(key=key)}
                    ),
                    STATUS_CODES["bad_request"],
                )

    # Validate path variables (if needed)
    if request.view_args:  # Check if view_args is not None
        for key, value in request.view_args.items():
            if not is_input_safe(value):
                return (
                    jsonify(
                        {"error": ERROR_MESSAGES["sql_injection_path"].format(key=key)}
                    ),
                    STATUS_CODES["bad_request"],
                )


@main_api.before_request
def pre_request_checks() -> Optional[Tuple[Any, int]]:
    """
    Combined before-request handler that runs all request-level validators.

    Behavior:
    - Validation (_validate_user_data) runs first. If it returns a response
      (indicating invalid input), that response is immediately returned to the
      client.
    - Rate limiting is handled by flask-limiter decorator on individual endpoints.

    Note: Flask will call all registered `before_request` handlers in the
    order they were registered. By centralizing into `pre_request_checks`, the
    order becomes explicit and easier to reason about.
    """

    # Run validation first
    resp = _validate_user_data()
    if resp is not None:
        return resp


def _sanitize_callback(callback: object, max_len: int = 200, fp_len: int = 12):
    """
    Normalize and redact untrusted callback text for safe logging.

    Returns a tuple (short_snippet, fingerprint) where short_snippet is a
    truncated, control-character-free, token-redacted string safe for logs,
    and fingerprint is a short HMAC-SHA256/sha256 hex prefix for correlation.
    """

    # Ensure string form
    raw = "" if callback is None else str(callback)

    # Normalize unicode to a stable form
    raw = unicodedata_normalize("NFKC", raw)

    # Collapse newlines/tabs into space and remove control characters
    raw = re_sub(r"[\r\n\t]+", " ", raw)
    raw = "".join(ch if unicodedata_category(ch)[0] != "C" else "?" for ch in raw)

    # Redact obvious JWTs (three base64url parts) and long base64-like tokens
    raw = re_sub(
        r"[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", "<REDACTED_JWT>", raw
    )
    raw = re_sub(r"[A-Za-z0-9_\-]{20,}", "<REDACTED_TOKEN>", raw)

    # Truncate to a safe length for logs
    short = (raw[:max_len] + "...") if len(raw) > max_len else raw

    # Compute fingerprint using HMAC with server secret if available, fallback to sha256
    try:
        key = (
            JWT_SECRET_KEY if "JWT_SECRET_KEY" in globals() and JWT_SECRET_KEY else None
        )
        if key:
            fp = hmac_new(
                str(key).encode("utf-8"), str(callback).encode("utf-8"), hashlib_sha256
            ).hexdigest()[:fp_len]
        else:
            fp = hashlib_sha256(str(callback).encode("utf-8")).hexdigest()[:fp_len]
    except Exception:
        fp = hashlib_sha256(short.encode("utf-8")).hexdigest()[:fp_len]

    return short, fp


# Rate limiting is handled by `flask-limiter` decorators and configuration.
# The previous `is_rate_limited` hook was removed to simplify runtime codepaths
# and avoid having two separate enforcement mechanisms. Tests should exercise
# the limiter behavior directly (e.g. by toggling `limiter.enabled` or using
# the `limiter` decorators on endpoints).


# Handle unauthorized access (missing token)
@jwt.unauthorized_loader
def custom_unauthorized_response(callback):
    """
    Handle requests with missing JWT tokens by logging the
    attempt and returning a standardized JSON error response.
    """

    # sanitize and fingerprint the callback before logging
    cb_short, cb_fp = _sanitize_callback(
        callback
    )  # get sanitized callback and fingerprint

    # Log the unauthorized access attempt
    log(
        message=f"API reached with missing token, callback: {cb_short} [fp:{cb_fp}]",
        level="ERROR",
        sd_tags={
            "host": API_SERVER_HOST,
            "port": API_SERVER_PORT,
        },
        message_id="MSNTOK",
        priority=1,  # High priority for security/auth failures
    )

    return (
        jsonify(INVALID_JWT_MESSAGES["missing_token"][0]),
        INVALID_JWT_MESSAGES["missing_token"][1],
    )


# Handle invalid tokens
@jwt.invalid_token_loader
def custom_invalid_token_response(callback):
    """
    Handle requests with invalid JWT tokens by logging the
    attempt and returning a standardized JSON error response.
    """

    # sanitize and fingerprint the callback before logging
    cb_short, cb_fp = _sanitize_callback(
        callback
    )  # get sanitized callback and fingerprint

    # Use the SQLiteUDPLogger instance
    log(
        message=f"API reached with invalid token, callback: {cb_short} [fp:{cb_fp}]",
        level="ERROR",
        sd_tags={
            "host": API_SERVER_HOST,
            "port": API_SERVER_PORT,
        },
        message_id="INVTOK",
        priority=1,  # High priority for security/auth failures
    )

    return (
        jsonify(INVALID_JWT_MESSAGES["invalid_token"][0]),
        INVALID_JWT_MESSAGES["invalid_token"][1],
    )


# Helper function to summarize JWT headers and payloads in logs
def _summarize(d: dict, keys: tuple):

    # if not a dict, return string representation
    if not isinstance(d, dict):
        return str(d)

    # extract specified keys with truncation
    out = {}
    for k in keys:
        if k in d:
            v = d[k]
            if isinstance(v, str) and len(v) > 64:
                v = v[:64] + "..."  # truncate long values
            out[k] = v

    # fallback: show first 5 keys if none of the specified keys found
    return out or {"keys": list(d.keys())[:5]}


# Handle expired tokens
@jwt.expired_token_loader
def custom_expired_token_response(jwt_header, jwt_payload):
    """
    Handle requests with expired JWT tokens by logging the attempt with summarized
    header and payload information, and returning a standardized JSON error response.
    """

    # summarize header and payload for logging
    header_summary = _summarize(jwt_header, ("alg", "typ", "kid", "jti"))
    payload_summary = _summarize(
        jwt_payload, ("sub", "identity", "jti", "exp", "role", "iss", "aud")
    )

    log(
        message=(
            "API reached with expired JWT. "
            f"Header summary: {header_summary}; Payload summary: {payload_summary}"
        ),
        level="ERROR",
        sd_tags={"host": API_SERVER_HOST, "port": API_SERVER_PORT},
        message_id="EXPTOK",
    )

    return (
        jsonify(INVALID_JWT_MESSAGES["expired_token"][0]),
        INVALID_JWT_MESSAGES["expired_token"][1],
    )


# Handle revoked tokens (if applicable)
@jwt.revoked_token_loader
def custom_revoked_token_response(jwt_header, jwt_payload):
    """
    Handle requests with revoked JWT tokens by logging the attempt with summarized
    header and payload information, and returning a standardized JSON error response.
    """
    # summarize header and payload for logging
    header_summary = _summarize(jwt_header, ("alg", "typ", "kid", "jti"))
    payload_summary = _summarize(
        jwt_payload, ("sub", "identity", "jti", "exp", "role", "iss", "aud")
    )

    log(
        message=(
            "API reached with revoked JWT. "
            f"Header summary: {header_summary}; Payload summary: {payload_summary}"
        ),
        level="ERROR",
        message_id="REVTOK",
        sd_tags={"host": API_SERVER_HOST, "port": API_SERVER_PORT},
    )

    return (
        jsonify(INVALID_JWT_MESSAGES["revoked_token"][0]),
        INVALID_JWT_MESSAGES["revoked_token"][1],
    )


# Endpoint to clear sent logs before a given timestamp
@jwt_required()
@main_api.route(f"/api/{API_VERSION}/logs/clear", methods=["POST"])
@limiter.limit(lambda: get_rate_limit("strict"))
def clear_sent_logs():
    """
    ---
    tags:
        - API Server (api_server)
    summary: Clear sent logs before a timestamp
    description: Deletes all logs marked as sent (sent=1) with timestamp before the given timestamp
    (expected in UTC, no timezone indicators, e.g. "2025-07-21 10:30:45").
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
    try:
        # Extract and validate admin authorization
        try:
            identity = get_jwt_identity()
        except RuntimeError:
            # JWT not present or invalid; return standardized missing token response
            return (
                jsonify(INVALID_JWT_MESSAGES["missing_token"][0]),
                INVALID_JWT_MESSAGES["missing_token"][1],
            )

        # Fetch user from database to check role
        from models import User

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
        timestamp_str: str = data.get("timestamp")

        # Check if timestamp is provided
        if not timestamp_str:
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
        num_deleted: int = log_interface.clear_sent_logs_before(before_timestamp)

        # Log action with structured data and message ID for observability
        log(
            message=f"Cleared {num_deleted} sent logs before {before_timestamp} (UTC)",
            level="INFO",
            sd_tags={"timestamp": timestamp_str},
            message_id="CLRLOGS",
        )

        # Return the number of deleted logs in the response
        return jsonify({"Successfully deleted logs": num_deleted}), STATUS_CODES["ok"]
    except Exception as ex:
        # Log the error with structured data and message ID for observability
        log(
            message=f"Internal server occurred while deleting logs (ex: {ex})",
            level="ERROR",
            sd_tags=(
                {"timestamp_str": timestamp_str}
                if "timestamp_str" in locals()
                else None
            ),
            message_id="CLRLOGSERR",
        )
        # return a generic error message without exposing internal details,
        # with appropriate status code
        return (
            jsonify(
                {
                    "Internal server error while deleting logs": "No more information given for "
                    "security purposes, check logs for further detail"
                }
            ),
            STATUS_CODES["internal_server_error"],
        )


@main_api.route(f"/api/{API_VERSION}/health", methods=["GET"]) 
def health_check():
    """Simple health check endpoint.

    Rate limiting for operational endpoints should be applied via
    `@limiter.limit(...)` decorators. The previous test hook was removed.
    """

    """
    ---
    tags:
      - API Server (api_server)
    summary: Health Check
    description: Returns the status of the API server.
    operationId: api_health_check
    responses:
      200:
        description: Server is running and healthy.
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

    # Register the blueprints
    blueprints_dir: str = os_path_join(
        os_path_dirname(os_path_abspath(__file__)), "api_blueprints"
    )

    # Ensure the api_blueprints directory exists and contains at least one Python file
    try:
        entries = os_listdir(blueprints_dir)
    except Exception as ex:
        # Log the error and exit if the directory is missing or inaccessible
        log(
            message=f"Blueprints directory '{blueprints_dir}' not found or inaccessible: {ex}",
            level="ERROR",
            message_id="BPLOADERR",
            sd_tags={
                "host": API_SERVER_HOST,
                "port": API_SERVER_PORT,
                "blueprints_dir": blueprints_dir,
            },
        )
        # Also print to console for immediate feedback
        print(f"ERROR: api_blueprints directory not found or inaccessible: {ex}")
        sys_exit(1)  # exit with error

    # Require at least one .py file to proceed (avoid starting with an empty blueprints dir)
    python_files = [f for f in entries if f.endswith(".py")]
    if not python_files:
        # if no Python files found, log and exit
        log(
            message=f"No Python files found in '{blueprints_dir}'. At least one file is required.",
            level="ERROR",
            message_id="BPLOADERR",
            sd_tags={
                "host": API_SERVER_HOST,
                "port": API_SERVER_PORT,
                "blueprints_dir": blueprints_dir,
            },
        )
        print(
            f"ERROR: No Python files found in {blueprints_dir}; add at least one blueprint file."
        )  # Print to console for immediate feedback
        sys_exit(1)  # exit with error

    for filename in os_listdir(blueprints_dir):
        # Only consider Python files following the *_bp.py naming convention
        # (i.e. files meant to define blueprints)
        if not filename.endswith("_bp.py"):
            continue

        module_name: str = filename[:-3]  # remove .py extension

        # Construct the full module name for import (e.g. api_blueprints.users_bp)
        full_module_name = f"api_blueprints.{module_name}"  # construct full import path
        # full_module_name is a constant

        # Try importing the module; log and continue on failure
        try:
            module = import_module(full_module_name)
        except Exception as ex:
            log(
                message=f"Failed to import blueprint module '{full_module_name}': {ex}",
                level="ERROR",
                message_id="BPLOADERR",
                sd_tags={
                    "host": API_SERVER_HOST,
                    "port": API_SERVER_PORT,
                    "module": full_module_name,
                },
            )
            print(f"Skipping {full_module_name}: import failed: {ex}")
            continue

        # Discover all flask.Blueprint instances in api_blueprints.<module>
        found_blueprints = []
        for attr_name in dir(module):

            # skip private attributes quickly
            if attr_name.startswith("_"):
                continue
            try:
                attr = getattr(module, attr_name)
            except Exception:
                # If accessing an attribute raises, skip it (but don't crash startup)
                continue

            # Only accept actual Flask Blueprint instances
            if isinstance(attr, Blueprint):
                found_blueprints.append((attr_name, attr))

        if not found_blueprints:
            # If the module doesn't export a Blueprint, log a warning and continue
            log(
                message=f"No Flask Blueprint found in module '{full_module_name}'.",
                level="WARNING",
                message_id="BPLOADWARN",
                sd_tags={
                    "host": API_SERVER_HOST,
                    "port": API_SERVER_PORT,
                    "module": full_module_name,
                },
            )
            print(f"No blueprint found in {full_module_name}; skipping.")
            continue

        # Register all discovered Blueprints
        for attr_name, blueprint in found_blueprints:
            try:
                main_api.register_blueprint(
                    blueprint, url_prefix=URL_PREFIX
                )  # Register with proper URL prefix
                # Log successful registration
                print(
                    f"Registered blueprint: {full_module_name}.{attr_name} with prefix {URL_PREFIX}"
                )
            except Exception as ex:
                log(
                    message=f"Failed to register blueprint '{full_module_name}.{attr_name}': {ex}",
                    level="ERROR",
                    message_id="BPLOADERR",
                    sd_tags={
                        "host": API_SERVER_HOST,
                        "port": API_SERVER_PORT,
                        "module": full_module_name,
                        "attribute": attr_name,
                    },
                )  # Log the error
                print(
                    f"Failed to register {full_module_name}.{attr_name}: {ex}"
                )  # Print to console for immediate feedback

    # Initialize the database inside the app context
    with main_api.app_context():
        try:
            db.create_all()
        except OperationalError as e:
            # Log a clear, structured message and exit cleanly
            # so startup doesn't crash with an opaque traceback
            log(
                message=f"Database connection failed during create_all: {e}",
                level="ERROR",
                message_id="DBCONNERR",
                sd_tags={"host": API_SERVER_HOST, "port": API_SERVER_PORT},
            )
            print(
                "ERROR: cannot connect to the database. Check Postgres is running "
                "and SQLALCHEMY_DATABASE_URI in config.\n"
                f"Current SQLALCHEMY_DATABASE_URI={SQLALCHEMY_DATABASE_URI}"
            )  # Print to console for immediate feedback
            sys_exit(1)  # exit with error

    # Start the server
    if API_SERVER_DEBUG_MODE is True:

        # Log server start event
        log(
            message="API server started with Flask built-in server "
            f"with debug mode set to {API_SERVER_DEBUG_MODE}",
            level="INFO",
            message_id="SRVSTART",
            sd_tags={"host": API_SERVER_HOST, "port": API_SERVER_PORT},
        )

        # Start the server with Flask's built-in server
        if (API_SERVER_SSL_CERT == "") != (API_SERVER_SSL_KEY == ""):
            raise ValueError(
                "Both SSL certificate and key must be provided, or both left empty"
            )
        else:
            main_api.run(
                host=API_SERVER_HOST,
                port=API_SERVER_PORT,
                debug=API_SERVER_DEBUG_MODE,
                ssl_context=(
                    (API_SERVER_SSL_CERT, API_SERVER_SSL_KEY)
                    if IS_API_SERVER_SSL
                    else None
                ),
            )

        # Log server stop event only if run() returns (which is rare, usually only on shutdown)
        log(
            message="API server stopped (Flask run() exited)",
            level="INFO",
            message_id="SRVSTOP",
            sd_tags={"host": API_SERVER_HOST, "port": API_SERVER_PORT},
        )

    else:
        try:
            # Log server start event
            log(
                message="API server started with waitress-serve",
                level="INFO",
                message_id="SRVSTART",
                sd_tags={"host": API_SERVER_HOST, "port": API_SERVER_PORT},
            )

            # Start the server with waitress
            cmd = [
                "waitress-serve",
                f"--host={API_SERVER_HOST}",
                f"--port={API_SERVER_PORT}",
            ]
            if IS_API_SERVER_SSL:
                cmd.append("--url-scheme=https")
            cmd.append("api_server:main_api")

            result = subprocess_run(cmd, capture_output=True, text=True)
            exit_code = result.returncode

            # Log shutdown event
            log(
                message=f"API server started with waitress shutdown with code {exit_code}",
                level="INFO",
                message_id="SRVSTOP",
                sd_tags={
                    "host": API_SERVER_HOST,
                    "port": API_SERVER_PORT,
                    "exit_code": exit_code,
                },
            )

        except Exception as ex:
            log(
                message=f"Exception while starting API server with waitress-serve: {ex}",
                level="ERROR",
                message_id="SRVSTARTERR",
                sd_tags={"host": API_SERVER_HOST, "port": API_SERVER_PORT},
            )
