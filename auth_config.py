"""
This module handles the .env file (checking if it exists and loading it) and defines all
the configuration variables for the authentication service in such a way that they are
easily readable from other parts of the code, which will see this file as a python module.
This module also provides default values and explanations for each configuration variable.
"""

# Library imports
from traceback import print_exc as traceback_print_exc
from sys import exit as sys_exit
from typing import Dict
from datetime import timedelta
from os import environ as os_environ
from re import IGNORECASE as RE_IGNORECASE, compile as re_compile
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from dotenv import load_dotenv

try:
    if not load_dotenv():  # Loads .env file if present
        raise FileNotFoundError("No .env file found.")
    print("Loaded environment variables from .env file in api_config.py")
except FileNotFoundError as ex:
    traceback_print_exc()  # Print full traceback for debugging
    input(
        "Close the program by closing this window.\n"
        "Input detection is not possible due to Flask blocking the terminal."
    )
    sys_exit(1)

# Authentication server related settings
AUTH_SERVER_HOST: str = os_environ.get(
    "AUTH_SERVER_HOST", "localhost"
)  # host to run the auth server on
AUTH_SERVER_PORT: int = int(
    os_environ.get("AUTH_SERVER_PORT", 5001)
)  # port to run the auth server on
AUTH_SERVER_IDENTIFIER: str = os_environ.get(
    "AUTH_SERVER_IDENTIFIER", "auth-server-1"
)  # identifier of the auth server (used to distinguish multiple auth servers if needed)
# (also the name that shows up in logs)
AUTH_API_VERSION: str = os_environ.get(
    "AUTH_API_VERSION", "v1"
)  # version of the auth API
AUTH_SERVER_DEBUG_MODE: bool = (
    os_environ.get("AUTH_SERVER_DEBUG_MODE", "True") == "True"
)  # enable/disable debug mode for flask built-in server
# (required to be False to simulate production environment) (see production_scripts/README.txt)
AUTH_SERVER_RATE_LIMIT: bool = (
    os_environ.get("AUTH_SERVER_RATE_LIMIT", "True") == "True"
)  # enable/disable rate limiting on the auth server
AUTH_SERVER_SSL_CERT: str = os_environ.get(
    "AUTH_SERVER_SSL_CERT", ""
)  # path to SSL certificate file (leave empty to disable SSL)
AUTH_SERVER_SSL_KEY: str = os_environ.get(
    "AUTH_SERVER_SSL_KEY", ""
)  # path to SSL key file (leave empty to disable SSL)
AUTH_SERVER_SSL: bool = not (
    AUTH_SERVER_SSL_CERT == "" and AUTH_SERVER_SSL_KEY == ""
)  # Whether the authentication server uses SSL/TLS or not

# PBKDF2 HMAC settings for password hashing (have to match those in api_config.py)
PBKDF2HMAC_SETTINGS: Dict[str, int] = {
    "algorithm": hashes.SHA256(),
    "length": 32,  # length of the derived key in bytes
    # (32 bytes = 256 bits, which is a common choice for secure password hashing)
    "iterations": 310_000,  # Minimum amount recommended by OWASP as of 2025
    # (should be increased if latency budget allows it)
    "backend": default_backend(),
}

# JWT custom configuration (must match those in api_config.py)
JWT_SECRET_KEY: str = os_environ.get(
    "JWT_SECRET_KEY", "Lorem ipsum dolor sit amet eget."
)  # secret key for signing JWTs
JWT_ALGORITHM: str = os_environ.get(
    "JWT_ALGORITHM", "HS256"
)  # algorithm used for signing JWTs
JWT_QUERY_STRING_NAME = os_environ.get(
    "JWT_QUERY_STRING_NAME", "jwt_token"
)  # name of the query string parameter for JWTs
JWT_JSON_KEY = os_environ.get(
    "JWT_JSON_KEY", "jwt_token"
)  # name of the JSON key for JWTs
JWT_REFRESH_JSON_KEY = os_environ.get(
    "JWT_REFRESH_JSON_KEY", "jwt_refresh_token"
)  # name of the JSON key for refresh JWTs
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

# Settings for logging interface
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
    "AUTH_SERVER_LOG_INTERFACE_DB_FILENAME", ""
)  # filename for the SQLite database file for logging
# (no default parameter is given, because if it is missing the interface will create
# a more accurately named DB file based on runtime (e.g. timestamps))
LOG_INTERFACE_MAX_RETRIES: int = int(
    os_environ.get("LOG_INTERFACE_MAX_RETRIES", 5)
)  # maximum number of retries for logging interface
LOG_INTERFACE_BATCH_DELAY: int = int(
    os_environ.get("LOG_INTERFACE_BATCH_DELAY", 30)
)  # delay (in seconds) between retries for logging interface

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
)  # disable/enable for flask-sql alchemy to track modifications
# (will have major performance impact, recommended to keep it disabled)

# Miscellaneous settings
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
