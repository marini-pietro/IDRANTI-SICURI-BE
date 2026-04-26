"""
This module handles the .env file (checking if it exists and loading it) and defines all
the configuration variables for the API service in such a way that they are easily readable
from other parts of the code, which will see this file as a python module.
This module also provides default values and explanations for each configuration variable.
"""

# Library imports
from traceback import print_exc as traceback_print_exc
from sys import exit as sys_exit
from re import IGNORECASE as RE_IGNORECASE, compile as re_compile
from datetime import timedelta
from os import environ as os_environ
from os.path import isfile as os_path_isfile
from typing import Any, Dict, Set, Tuple
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from dotenv import load_dotenv

if load_dotenv():  # Loads .env file if present
    print("Loaded environment variables from .env file in api_config.py")
else:
    print(
        "No .env file found in api_config.py; using defaults and environment variables."
    )

# Authentication server related settings
AUTH_SERVER_HOST: str = os_environ.get("AUTH_SERVER_HOST", "localhost")
AUTH_SERVER_PORT: int = int(os_environ.get("AUTH_SERVER_PORT", 5001))
AUTH_API_VERSION: str = os_environ.get("AUTH_API_VERSION", "v1")
IS_AUTH_SERVER_SSL: bool = os_environ.get("IS_AUTH_SERVER_SSL", "False") == "True"
JWT_VALIDATION_CACHE_SIZE: int = int(os_environ.get("JWT_VALIDATION_CACHE_SIZE", 1000))
JWT_VALIDATION_CACHE_TTL: int = int(os_environ.get("JWT_VALIDATION_CACHE_TTL", 3600))

# PBKDF2 HMAC settings for password hashing (have to match those in auth_config.py)
PBKDF2HMAC_SETTINGS: Dict[str, int | hashes.HashAlgorithm] = {
    "algorithm": hashes.SHA256(),
    "length": 32,  # length of the derived key in bytes (32 bytes = 256 bits,
    # which is a common choice for secure password hashing)
    "iterations": 310_000,  # Minimum amount recommended by OWASP as of 2025
    # (should be increased if latency budget allows it)
    "backend": default_backend(),
}

# Settings for loggin interface
# N.B: LOG_SERVER_HOST and LOG_SERVER_PORT must be valid and reachable
# by the auth server for logging to work properly
# N.B: LOG_DB_PATH must be a valid path where the auth server has write permissions
LOG_SERVER_HOST: str = os_environ.get(
    "LOG_SERVER_HOST", "localhost"
)  # host in which the log server listens for UDP syslog messages
LOG_SERVER_PORT: int = int(
    os_environ.get("LOG_SERVER_PORT", 514)
)  # port in which the log server listens for UDP syslog messages
LOG_INTERFACE_DB_FILENAME: str = os_environ.get(
    "API_SERVER_LOG_INTERFACE_DB_FILENAME", ""
)  # filename for the SQLite database file for logging
# (no default parameter is given, becuase if it is missing the interface will create
# a more accurately named DB file based on runtime data such as timestamps)
LOG_INTERFACE_MAX_RETRIES: int = int(
    os_environ.get("LOG_INTERFACE_MAX_RETRIES", 5)
)  # maximum number of retries for logging interface
LOG_INTERFACE_BATCH_DELAY: int = int(
    os_environ.get("LOG_INTERFACE_BATCH_DELAY", 15)
)  # delay (in seconds) between batch of logs sent to the log server by the logging interface

# API server related settings
API_SERVER_HOST: str = os_environ.get(
    "API_SERVER_HOST", "localhost"
)  # host to run the API server on
API_SERVER_PORT: int = int(
    os_environ.get("API_SERVER_PORT", 5000)
)  # port to run the API server on
API_SERVER_IDENTIFIER: str = os_environ.get(
    "API_SERVER_IDENTIFIER", "api-server-1"
)  # identifier of the API server (used to distinguish multiple api servers if needed)
# (also the name that shows up in logs)
API_VERSION: str = os_environ.get("API_VERSION", "v1")  # version of the API
URL_PREFIX: str = f"/api/{API_VERSION}"  # prefix for all API endpoints
API_SERVER_DEBUG_MODE: bool = (
    os_environ.get("API_SERVER_DEBUG_MODE", "True") == "True"
)  # enable/disable debug mode for flask built-in server (required to be False to
# simulate production environment) (see production_scripts/README.txt)
API_SERVER_RATE_LIMIT: bool = (
    os_environ.get("API_SERVER_RATE_LIMIT", "True") == "True"
)  # enable/disable rate limiting on the API server
API_SERVER_MAX_JSON_SIZE = int(
    os_environ.get("API_SERVER_MAX_JSON_SIZE", 50 * 10244)
)  # max size (in bytes) of incoming JSON payloads
SQL_SCAN_MAX_LEN = int(
    os_environ.get("SQL_SCAN_MAX_LEN", 2048)
)  # max length of input strings to scan for SQL injection attempts
SQL_SCAN_MAX_RECURSION_DEPTH = int(
    os_environ.get("SQL_SCAN_MAX_RECURSION_DEPTH", 10)
)  # max recursion depth when scanning nested data structures for SQL injection attempts
LOGIN_AVAILABLE_THROUGH_API: bool = AUTH_SERVER_HOST in {
    "localhost",
    "127.0.0.1",
}  # whether login endpoint is available through the API server
# in some cases (e.g. when the same machine hosts both the API server and the auth server)
# it might desireable for security reasons to only expose to the public the API server and
# have it redirect login requests to the auth server running on localhost
# (based on case-by-case needs the IP address can be added or removed to the set above)
API_SERVER_SSL_CERT: str = os_environ.get(
    "API_SERVER_SSL_CERT", ""
)  # path to SSL certificate file (leave empty (i.e. "") to disable SSL)
API_SERVER_SSL_KEY: str = os_environ.get(
    "API_SERVER_SSL_KEY", ""
)  # path to SSL key file (leave empty (i.e. "") to disable SSL)
IS_API_SERVER_SSL: bool = not (
    API_SERVER_SSL_CERT == "" and API_SERVER_SSL_KEY == ""
)  # whether the API server uses SSL/TLS or not
# Validate SSL certificate and key files
if IS_API_SERVER_SSL:
    if not os_path_isfile(API_SERVER_SSL_CERT):
        raise FileNotFoundError(
            f"SSL certificate file not found: {API_SERVER_SSL_CERT}"
        )
    if not os_path_isfile(API_SERVER_SSL_KEY):
        raise FileNotFoundError(f"SSL key file not found: {API_SERVER_SSL_KEY}")
    if not API_SERVER_SSL_CERT.endswith((".crt", ".pem", ".cer")):
        raise ValueError(f"Invalid SSL certificate extension: {API_SERVER_SSL_CERT}")
    if not API_SERVER_SSL_KEY.endswith((".key", ".pem")):
        raise ValueError(f"Invalid SSL key extension: {API_SERVER_SSL_KEY}")

# JWT custom configuration
JWT_SECRET_KEY: str = os_environ.get(
    "JWT_SECRET_KEY", "Lorem ipsum dolor sit amet eget."
)  # secret key for signing JWTs
JWT_ALGORITHM: str = os_environ.get(
    "JWT_ALGORITHM", "HS256"
)  # algorithm used for signing JWTs
JWT_QUERY_STRING_NAME = os_environ.get(
    "JWT_QUERY_STRING_NAME", "jwt_token"
)  # name of the query string parameter to look for JWTs
# (if JWTs are sent via query string, not recommended for production)
JWT_JSON_KEY = os_environ.get(
    "JWT_JSON_KEY", "jwt_token"
)  # name of the JSON key to look for JWTs (if JWTs are sent via JSON body)
JWT_REFRESH_JSON_KEY = os_environ.get(
    "JWT_REFRESH_JSON_KEY", "jwt_refresh_token"
)  # name of the JSON key to look for refresh JWTs (if refresh JWTs are sent via JSON body)
JWT_TOKEN_LOCATION = os_environ.get(
    "JWT_TOKEN_LOCATION",
    "headers,query_string,json",  # values must be strictly separated by commas with no spaces
).split(
    ","
)  # locations to look for JWTs
JWT_REFRESH_TOKEN_EXPIRES = timedelta(
    days=int(os_environ.get("JWT_REFRESH_TOKEN_EXPIRES_DAYS", 10))
)  # refresh token expiration time
JWT_ACCESS_TOKEN_EXPIRES = timedelta(
    hours=int(os_environ.get("JWT_ACCESS_TOKEN_EXPIRES_HOURS", 3))
)  # access token expiration time

# Database configuration
DB_HOST = os_environ.get("DB_HOST", "localhost")  # database host
DB_NAME = os_environ.get("DB_NAME", "idranti-sicuri")  # database name
DB_USER = os_environ.get("DB_USER", "postgres")  # database user
DB_PASSWORD = os_environ.get("DB_PASSWORD", "postgres")  # database password
DB_PORT = os_environ.get("DB_PORT", "5432")  # database port
# database URI for SQLAlchemy (format: postgresql://user:password@host:port/dbname)
SQLALCHEMY_DATABASE_URI = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
SQLALCHEMY_TRACK_MODIFICATIONS = (
    os_environ.get("SQLALCHEMY_TRACK_MODIFICATIONS", "False") == "True"
)  # disable/enable flask sql alchemy track modifications
# (will have major performance impact, recommended to keep it disabled)


# Rate limiting settings
RATE_LIMIT_MAX_REQUESTS: int = int(
    os_environ.get("RATE_LIMIT_MAX_REQUESTS", 50)
)  # max requests per time window
RATE_LIMIT_CACHE_SIZE: int = int(
    os_environ.get("RATE_LIMIT_CACHE_SIZE", 1000)
)  # number of unique clients to track
RATE_LIMIT_CACHE_TTL: int = int(
    os_environ.get("RATE_LIMIT_CACHE_TTL", 10)
)  # time window (in seconds) for rate limiting

# HTTP status codes
STATUS_CODES: Dict[str, int] = {
    "not_found": 404,
    "unauthorized": 401,
    "forbidden": 403,
    "conflict": 409,
    "precondition_failed": 412,
    "unprocessable_entity": 422,
    "too_many_requests": 429,
    "gateway_timeout": 504,
    "bad_request": 400,
    "created": 201,
    "ok": 200,
    "no_content": 204,
    "internal_error": 500,
    "service_unavailable": 503,
}

# Roles and their corresponding IDs
ROLES: Set[str] = {"admin", "operator", "viewer"}

# Standard not authorized message
NOT_AUTHORIZED_MESSAGE: Dict[str, str] = {
    "outcome": "error, action not permitted with current user"
}

# Regex pattern for SQL injection detection
# This regex pattern is used to detect SQL injection attempts in user input.
# It matches common SQL keywords and commands that are often used in SQL injection attacks.
# Precompile the regex pattern once
SQL_PATTERN = re_compile(
    r"\b("
    + "|".join(
        [
            r"SELECT",
            r"INSERT",
            r"UPDATE",
            r"DELETE",
            r"DROP",
            r"CREATE",
            r"ALTER",
            r"EXEC",
            r"EXECUTE",
            r"SHOW",
            r"DESCRIBE",
            r"USE",
            r"LOAD",
            r"INTO",
            r"OUTFILE",
            r"INFORMATION_SCHEMA",
            r"DATABASES",
            r"SCHEMAS",
            r"COLUMNS",
            r"VALUES",
            r"UNION",
            r"ALL",
            r"WHERE",
            r"FROM",
            r"TABLE",
            r"JOIN",
            r"TRUNCATE",
            r"REPLACE",
            r"GRANT",
            r"REVOKE",
            r"DECLARE",
            r"CAST",
            r"SET",
            r"LIKE",
            r"OR",
            r"AND",
            r"HAVING",
            r"LIMIT",
            r"OFFSET",
            r"ORDER BY",
            r"GROUP BY",
            r"CONCAT",
            r"SLEEP",
            r"BENCHMARK",
            r"IF",
            r"ASCII",
            r"CHAR",
            r"HEX",
        ]
    )
    + r")\b"
    + r"|(--|#|;)",  # Match special characters without word boundaries
    RE_IGNORECASE,
)

# Flasgger (Swagger UI) configuration
SWAGGER_CONFIG: Dict[str, Any] = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            # "rule_filter" and "model_filter" are used to specify which
            # endpoints and models to include in the Swagger documentation.
            # Including all endpoints and models by returning True for all
            # (type: ignore to suppress pylance strict type check warnings).
            "rule_filter": lambda rule: True,  # type: ignore
            "model_filter": lambda tag: True,  # type: ignore
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs/",
}

# Invalid JWT token related messages
# Store plain payload dicts and status codes as a SSOT (single source of truth);
# call jsonify() inside request handlers to have consistent responses
INVALID_JWT_MESSAGES: Dict[str, Tuple[Dict[str, str], int]] = {
    "missing_token": ({"error": "missing token"}, STATUS_CODES["unauthorized"]),
    "invalid_token": (
        {"error": "provided token is invalid"},
        STATUS_CODES["unprocessable_entity"],
    ),
    "expired_token": (
        {"error": "provided token is expired"},
        STATUS_CODES["unauthorized"],
    ),
    "revoked_token": (
        {"error": "provided token has been revoked"},
        STATUS_CODES["unauthorized"],
    ),
}
