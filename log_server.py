"""
Syslog server implementation that listens for syslog messages over UDP.
It processes messages according to RFC 5424, implements rate limiting,
and logs messages to both console and file.
It also handles delayed logs when the rate limit is exceeded.
"""

# Library imports
import logging
from time import sleep as time_sleep
from threading import Thread, Lock, Event as threading_Event
from typing import List, Tuple, Deque, Optional
from json import loads as json_loads
from json import JSONDecodeError
from os.path import abspath as os_path_abspath
from os.path import dirname as os_path_dirname
from os.path import join as os_path_join
import os
import socket as socket_lib
from selectors import DefaultSelector as selectors_DefaultSelector
from selectors import EVENT_READ as selectors_EVENT_READ
from datetime import datetime
from collections import defaultdict, deque
from cachetools import TTLCache

# Local imports
from configs.log_config import (
    LOG_SERVER_HOST,
    LOG_SERVER_PORT,
    LOG_FILE_NAME,
    LOGGER_NAME,
    LOG_SERVER_IDENTIFIER,
    LOG_SERVER_RATE_LIMIT,
    DELAYED_LOGS_QUEUE_SIZE,
    RETAIN_LOGS_RATE_LIMIT_TRIGGER,
    LOG_RATE_LIMIT_TRIGGER_EVENTS,
    LOG_SERVER_RATE_LIMIT_MAX_REQUESTS,
    LOG_SERVER_RATE_LIMIT_CACHE_SIZE,
    LOG_SERVER_RATE_LIMIT_CACHE_TTL,
)


# Define the logger class
class Logger:
    """
    Logger class to handle logging messages to both console and file.
    """

    def __init__(self, log_file: str, console_level: int, file_level: int) -> None:
        """
        Initialize the logger with console and file handlers.
        """
        # Create a logger object
        self.logger: logging.Logger = logging.getLogger(name=LOGGER_NAME)
        self.logger.setLevel(logging.DEBUG)
        # Prevent log messages from being propagated to the root logger (avoids duplicates)
        self.logger.propagate = False

        # Create a console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_level)

        # Create a file handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(file_level)

        # Create formatter objects and set the format of the log messages
        # Format: timestamp - log level - message
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)

        # Add handlers to the logger only if they are not already present
        if not self.logger.handlers:
            self.logger.addHandler(console_handler)
            self.logger.addHandler(file_handler)

    # Function to log messages with different levels
    # (automatically retrieves the right function based on the log type parameter)
    # The log_type parameter should be one of the logging levels:
    # debug, info, warning, error, critical
    def log(self, log_type: str, message: str, origin: str) -> None:
        """
        Log a message with the specified type, message and origin.
        """

        log_method = getattr(
            self.logger, log_type
        )  # Get the logging method based on log_type
        log_method(
            f"[{origin}] {message}"
        )  # Call the method to log the message with origin info

    # Function to close all handlers
    def close(self) -> None:
        """
        Close all handlers of the logger.
        """

        for handler in self.logger.handlers[
            :
        ]:  # [:] copies the list to avoid modification during iteration
            handler.close()
            self.logger.removeHandler(handler)


# Generate the log file path inside a 'logs' subdirectory next to this script
logs_dir: str = os_path_join(os_path_dirname(os_path_abspath(__file__)), "logs")
os.makedirs(logs_dir, exist_ok=True) # Ensure the logs directory exists (if it doesn't exist, it will be created)
log_file_path: str = os_path_join(logs_dir, LOG_FILE_NAME)

# Initialize the logger
logger = Logger(
    log_file=log_file_path, console_level=logging.INFO, file_level=logging.DEBUG
)

# Add a shutdown flag
shutdown_flag: threading_Event = threading_Event()


def start_syslog_server(host: str, port: int) -> None:
    """
    Start a UDP-based syslog server that listens on both IPv4 and IPv6 addresses.
    This function attempts to bind two dedicated UDP sockets (one IPv6, one IPv4)
    for the provided host and port and then uses a selectors.DefaultSelector to
    monitor them for incoming datagrams. Each successfully bound socket is set to
    non-blocking mode and registered with the selector for read events so the
    selector will notify the loop when there is data available to be read from the
    socket.
    Behavior and features:
    - Resolves and binds addresses using socket.getaddrinfo(..., AI_PASSIVE), trying
        IPv6 first then IPv4.
    - The main loop polls the selector with a 1 second timeout and exits when the
        global shutdown_flag is set (or on KeyboardInterrupt).
    - Incoming datagrams are received with recvfrom(65535). Data is decoded as UTF-8;
        if decoding fails, invalid sequences are replaced and a warning is emitted via
        logger.log with an origin identifying the source IP.
    - Received messages are handed off to syslog_message_preprocessing(message, addr) for
        application-level handling.
    - Socket and selector errors during recvfrom are skipped (socket remains in use).
    - On shutdown, the function sets shutdown_flag, unregisters and closes all
        sockets, closes the selector, and calls logger.close() to tidy up resources.
    Parameters:
    - host (str | None): The local interface or hostname to bind to (may be None or
        "" to bind all interfaces).
    - port (int | str): The UDP port (or service name) to listen on.
    Return value:
    - None. The function runs a blocking polling loop until shutdown_flag is set or
        a KeyboardInterrupt occurs.
    """

    socket_selector = selectors_DefaultSelector()
    sockets: List[Optional[socket_lib.socket]] = []

    # Helper to attempt bind for a specific address family
    def _bind_for_family(family: int) -> Optional[socket_lib.socket]:
        try:
            addrinfos = socket_lib.getaddrinfo(
                host=host,
                port=port,
                family=family,
                type=socket_lib.SOCK_DGRAM,
                flags=socket_lib.AI_PASSIVE,
            )
        except socket_lib.gaierror:
            return None

        # Try each address until bind operations is successful
        for (
            ip_address_family,
            _,
            _,
            _,
            server_addr,
        ) in addrinfos:  # _ represents ignored values not used in this context
            socket = None
            try:
                socket = socket_lib.socket(ip_address_family, socket_lib.SOCK_DGRAM)
                # On IPv6, try to allow dual-stack where supported (this doesn't replace two-socket approach)
                if ip_address_family == socket_lib.AF_INET6:
                    try:
                        socket.setsockopt(
                            socket_lib.IPPROTO_IPV6, socket_lib.IPV6_V6ONLY, 0
                        )
                    except Exception:
                        pass
                socket.bind(server_addr)  # Bind the socket to the address
                return socket  # Return the successfully bound socket
            except OSError:
                if socket is not None:
                    try:
                        socket.close()  # Close the socket on failure
                    except Exception:
                        pass
                continue
        return None

    # Try to create both IPv6 and IPv4 sockets (IPv6 first)
    ipv6_socket = _bind_for_family(socket_lib.AF_INET6)
    ipv4_socket = _bind_for_family(socket_lib.AF_INET)

    # Add the successfully bound sockets to the list of available sockets
    if ipv6_socket:
        sockets.append(ipv6_socket)
    if ipv4_socket:
        sockets.append(ipv4_socket)

    # Print binding status
    if ipv6_socket and ipv4_socket:
        print(f"Syslog server bound to both IPv6 and IPv4, listening on {host}:{port}")
    elif ipv6_socket and not ipv4_socket:
        print(f"Syslog server bound to IPv6 only, listening on {host}:{port}")
    elif ipv4_socket and not ipv6_socket:
        print(f"Syslog server bound to IPv4 only, listening on {host}:{port}")
    if not sockets:
        print(
            f"Failed to bind both UDP sockets on {host}:{port}\n"
            "Is another instance of the log server already running or is the port in use?"
        )
        return

    # Now that we have our socket(s), set them to non-blocking and register them with the selector

    # Filter out any None sockets (in case one of the bind attempts failed) and set up the selector
    for socket in [s for s in sockets if s is not None]:
        socket.setblocking(
            False
        )  # Make socket non-blocking (I/O calls won't block the thread execution)
        socket_selector.register(
            socket, selectors_EVENT_READ
        )  # Register socket for read events

    try:
        while not shutdown_flag.is_set():
            events = socket_selector.select(timeout=1.0)
            if not events:  # If there are no events, continue to the next iteration
                continue
            for key, _ in events:
                sock: selectors_FileDescriptorLike = (
                    key.fileobj
                )  # Get the socket object from the selector key
                try:
                    # Receive data from the socket
                    data, addr = sock.recvfrom(
                        65535
                    )  # buffer size set to maximum UDP size to reduce risk of truncation
                    # UPD related fragmentation can still occur;
                    # handling of fragmented messages is not implemented
                    # becuase of the low likelihood of occurrence in typical syslog use cases
                except OSError:
                    # Socket error — skip this socket for now
                    continue

                # Decode the received data
                try:
                    message = data.decode("utf-8")  # Decode as UTF-8
                except (
                    UnicodeDecodeError
                ):  # If decoding fails, replace invalid sequences
                    message = data.decode("utf-8", errors="replace")
                    logger.log(  # Log a warning about the decoding issue
                        log_type="warning",
                        message=(
                            "Received non-UTF8 bytes from client — replaced invalid sequences "
                            f"in message: {message}"
                        ),
                        origin=LOG_SERVER_IDENTIFIER,
                    )

                # Hand off the message to the processing function
                syslog_message_preprocessing(message, addr)

    except KeyboardInterrupt:
        print("Shutting down syslog server...")
    # Regardless of how we exit the loop, ensure all resources are cleaned up
    finally:
        shutdown_flag.set()  # Set the shutdown flag so that the loop in the threads can exit gracefully
        for socket in sockets:
            try:
                socket_selector.unregister(
                    socket
                )  # Unregister the socket from the selector
            except Exception:  # Ignore errors during unregistering
                pass
            try:
                socket.close()  # Close the socket
            except Exception:  # Ignore errors during socket close
                pass
        try:
            socket_selector.close()  # Close the selector
        except Exception:  # Ignore errors during selector close
            pass
        logger.close()  # Close the logger


# TTL cache to track request counts for rate limiting (keyed by client IP)
rate_limit_cache = TTLCache(
    maxsize=LOG_SERVER_RATE_LIMIT_CACHE_SIZE, ttl=LOG_SERVER_RATE_LIMIT_CACHE_TTL
)
rate_limit_lock = Lock()  # Lock for thread-safe file access


def enforce_rate_limit(client_ip: str) -> bool:
    """
    Check if the client IP is rate-limited using an in-memory TTLCache.
    (This function will return true (the rate has been exceeded) on the exact request
    that matches the limit, i.e. the 100th request is the limit is 100 requests per time window)
    """

    with rate_limit_lock:
        # Retrieve or initialize client data
        client_data = rate_limit_cache.get(client_ip, {"count": 0})

        # Increment the request count
        client_data["count"] += 1

        # Update the cache with the new client data
        rate_limit_cache[client_ip] = client_data

        # Check if the rate limit is exceeded
        return client_data["count"] > LOG_SERVER_RATE_LIMIT_MAX_REQUESTS


# Only create the deque and lock for delayed logs if the feature
# is enabled to avoid unnecessary resource usage when it's not needed
if RETAIN_LOGS_RATE_LIMIT_TRIGGER is True:

    # Queue to store delayed logs
    delayed_logs: Deque[Tuple[str, tuple]] = deque(
        maxlen=DELAYED_LOGS_QUEUE_SIZE
    )  # Limit the size of the queue to avoid memory issues
    queue_lock = Lock()  # Lock to ensure thread-safe access to the queue


def syslog_message_preprocessing(message: str, addr: tuple[str, int]) -> None:
    """
    Process and log a syslog message according to RFC 5424 with shared rate limiting.

    Parameters
    ----------
    message:
        Decoded syslog message (expected RFC 5424-like format).
    addr:
        Remote address tuple as returned by socket.recvfrom (ip, port, ...).

    Returns
    -------
    None
    """

    source_ip: str = addr[0]  # Extract source IP from address tuple

    # Enforce rate limit
    if LOG_SERVER_RATE_LIMIT is True:
        if enforce_rate_limit(source_ip):
            # Add the log to the delayed queue instead of dropping it (if enabled)
            if RETAIN_LOGS_RATE_LIMIT_TRIGGER is True:
                with queue_lock:
                    delayed_logs.append((message, addr))

            # Log the rate limit event if enabled
            if LOG_RATE_LIMIT_TRIGGER_EVENTS is True:
                logger.log(
                    log_type="warning",
                    message=f"{source_ip} exceeded rate limit. Delaying message: {message}",
                    origin=LOG_SERVER_IDENTIFIER,
                )

            return

    # Process the syslog message as usual
    _process_message(message)


def _process_message(message: str) -> None:
    """
    Helper function to parse and log a single syslog message.

    This function assumes `message` is a decoded string and `addr` is the
    address tuple from recvfrom(). It will parse the message as JSON
    and emit structured logs via `logger`.
    """
    try:
        # Parse the message as JSON
        log_data = json_loads(message)

        # Extract fields from JSON
        level = log_data.get("level", "INFO").upper()
        service = log_data.get("service", "unknown-service")
        timestamp = log_data.get("timestamp", "")
        process_id = log_data.get("process_id", "-")
        message_id = log_data.get("message_id", "-")
        msg_content = log_data.get("message", "")
        tags = log_data.get("tags", {})
        hostname = log_data.get("hostname", "unknown-hostname")

        # Convert level to log server's log_type
        level_map = {
            "DEBUG": "debug",
            "INFO": "info",
            "WARNING": "warning",
            "ERROR": "error",
            "CRITICAL": "critical",
        }
        log_type = level_map.get(level, "info")

        # Format the message in RFC 5424 style
        # Facility 1 (user-level), severity from level
        severity_map = {"DEBUG": 7, "INFO": 6, "WARNING": 4, "ERROR": 3, "CRITICAL": 2}
        severity = severity_map.get(level, 6)
        priority = (1 << 3) | severity  # Facility 1, user-level

        # Format timestamp for RFC 5424 (if provided, otherwise use '-')
        rfc_timestamp = timestamp.replace(" ", "T") if timestamp else "-"

        # Create structured data from tags
        structured_data = "-"
        if tags:  # If there are tags, format them as structured data elements
            sd_elements: list[str] = []  # List to hold structured data elements

            # Iterate over tags and format them as key="value" pairs
            for key, value in tags.items():
                sd_elements.append(f'{key}="{value}"')

            # Source IP and source port cannot be added here because the syslog server only knows the data
            # of the logging interface not the original sender of the log message
            # so those kind of values must be passed as part of the tags by the logging interface itself if needed

            # Format final structured data string
            structured_data = f'[{service}@32473 {" ".join(sd_elements)}]'

        # Create RFC 5424 formatted message
        # 1 is the version of the syslog protocol (RFC 5424 always uses version 1)
        rfc_message = f"<{priority}>1 {rfc_timestamp} {hostname} {service} {process_id} {message_id} {structured_data} {msg_content}"

        # Log with RFC 5424 format
        logger.log(
            log_type=log_type,
            message=rfc_message,
            origin=LOG_SERVER_IDENTIFIER,
        )

    except JSONDecodeError:
        # Log a warning for invalid JSON messages
        logger.log(
            log_type="warning",
            message=f"Invalid JSON message received: {message}",
            origin=LOG_SERVER_IDENTIFIER,
        )
    except Exception as ex:
        # Log any other parsing errors
        logger.log(
            log_type="error",
            message=f"Error processing message: {ex}. Message: {message}",
            origin=LOG_SERVER_IDENTIFIER,
        )


def process_delayed_logs() -> None:
    """
    Periodically process delayed logs from the queue.

    This background worker will dequeue delayed messages and process them
    with the same parsing/validation logic as real-time messages. It exits
    when `shutdown_flag` is set.
    """
    while not shutdown_flag.is_set():  # Check the shutdown flag
        with queue_lock:
            if delayed_logs:
                # Dequeue the oldest delayed log
                # (address is not used in processing but could be logged if needed)
                message, _addr = delayed_logs.popleft()
                _process_message(message)

        time_sleep(0.1)  # Adjust the sleep interval as needed


# Start a background thread to process delayed logs
# Set to behave as a daemon so it will not block program exit
# (in that case, all remaining delayed logs will be lost on shutdown)
if RETAIN_LOGS_RATE_LIMIT_TRIGGER is True:
    Thread(target=process_delayed_logs, daemon=True).start()

if __name__ == "__main__":

    # Log server startup event
    logger.log(
        log_type="info",
        message="Starting syslog server...",
        origin=LOG_SERVER_IDENTIFIER,
    )

    try:
        # Start the syslog server
        start_syslog_server(LOG_SERVER_HOST, LOG_SERVER_PORT)

    except KeyboardInterrupt:

        logger.close()  # Ensure logger is closed on user interrupt

        logger.log(
            log_type="info",
            message="Syslog server stopped by user via KeyboardInterrupt.",
            origin=LOG_SERVER_IDENTIFIER,
        )
    except Exception as ex:

        logger.close()  # Ensure logger is closed on exception

        logger.log(
            log_type="warning",
            message=f"Syslog server encountered the following exception: {ex}",
            origin=LOG_SERVER_IDENTIFIER,
        )
