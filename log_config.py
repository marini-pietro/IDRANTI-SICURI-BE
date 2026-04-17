"""
This module handles the .env file (checking if it exists and loading it) and defines all
the configuration variables for the log server in such a way that they are easily readable
from other parts of the code, which will see this file as a python module.
This module also provides default values and explanations for each configuration variable.
"""

# Library imports
from sys import exit as sys_exit
from traceback import print_exc as traceback_print_exc
from os import environ as os_environ
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

# Log server related settings
LOG_SERVER_HOST: str = os_environ.get(
    "LOG_SERVER_HOST", "localhost"
)  # host on which the log server listens for incoming syslog messages
LOG_SERVER_PORT: int = int(
    os_environ.get("LOG_SERVER_PORT", 5002)
)  # port on which the log server listens for incoming syslog messages
LOG_FILE_NAME: str = os_environ.get(
    "LOG_FILE_NAME", "idranti-sicuri_log.txt"
)  # name of the log file where logs are stored
LOGGER_NAME: str = os_environ.get(
    "LOGGER_NAME", "idranti-sicuri_logger"
)  # name of the logger used in the log server
LOG_SERVER_IDENTIFIER: str = os_environ.get(
    "LOG_SERVER_IDENTIFIER", "log-server-1"
)  # identifier of the log server (used to distinguish multiple log servers if needed)
# (also the name that shows up in logs)
LOG_SERVER_RATE_LIMIT: bool = (
    os_environ.get("LOG_SERVER_RATE_LIMIT", "True") == "True"
)  # enable/disable rate limiting on the log server
DELAYED_LOGS_QUEUE_SIZE: int = int(
    os_environ.get("DELAYED_LOGS_QUEUE_SIZE", 100)
)  # Size of the queue for delayed logs
# (if the queue is full, the oldest logs will
#  be removed to make space for new ones)
RETAIN_LOGS_RATE_LIMIT_TRIGGER: bool = (
    os_environ.get("RETAIN_LOGS_RATE_LIMIT_TRIGGER", "True") == "True"
)  #  Whether to retain logs (but not process them immediately) when rate limit is triggered
LOG_RATE_LIMIT_TRIGGER_EVENTS: bool = (
    os_environ.get("LOG_RATE_LIMIT_TRIGGER_EVENTS", "False") == "True"
)  # Whether or not to log rate limit trigger events (log that an ip has been rate limited)

# Rate limiting settings
LOG_SERVER_RATE_LIMIT_MAX_REQUESTS: int = int(
    os_environ.get("LOG_SERVER_RATE_LIMIT_MAX_REQUESTS", 50)
)  # max requests per time window
LOG_SERVER_RATE_LIMIT_CACHE_SIZE: int = int(
    os_environ.get("LOG_SERVER_RATE_LIMIT_CACHE_SIZE", 1000)
)  # number of unique clients to track
LOG_SERVER_RATE_LIMIT_CACHE_TTL: int = int(
    os_environ.get("LOG_SERVER_RATE_LIMIT_CACHE_TTL", 10)
)  # time window (in seconds) for rate limiting
