"""
Tests for log_server rate limiting and JSON message processing.
"""

import json
import importlib
import logging
import re
import sys
import types

# log_server imports EVENT_READ from a third-party `selector` module.
# Provide a lightweight stub so tests can import the module in environments
# where the dependency is not installed.
if "selector" not in sys.modules:
    selector_stub = types.ModuleType("selector")
    selector_stub.EVENT_READ = 1
    sys.modules["selector"] = selector_stub

log_server = importlib.import_module("log_server")


def test_enforce_rate_limit_counters():
    """
    Rate limiter should trigger only after the configured threshold is exceeded.
    """

    log_server.rate_limit_cache.clear()
    client_ip = "1.2.3.4"
    max_req = log_server.LOG_SERVER_RATE_LIMIT_MAX_REQUESTS

    for _ in range(max_req):
        assert log_server.enforce_rate_limit(client_ip) is False
    assert log_server.enforce_rate_limit(client_ip) is True


def test_process_message_parsing_and_logging(monkeypatch):
    """
    _process_message should parse valid JSON and emit structured info logs.
    """

    calls = []

    class DummyLogger:
        """
        Minimal logger double used to capture emitted log records.
        """

        def log(self, log_type, message, origin, include_timestamp=False):
            calls.append((log_type, message, origin))

        def close(self):
            """No-op close required by logger contract."""

    monkeypatch.setattr(log_server, "logger", DummyLogger())

    payload = {
        "level": "INFO",
        "service": "api",
        "timestamp": "2026-04-23 10:30:00",
        "process_id": "123",
        "message_id": "TESTID",
        "message": "hello world",
        "tags": {"endpoint": "/health"},
        "hostname": "localhost",
    }
    log_server._process_message(json.dumps(payload))

    assert len(calls) == 1
    assert calls[0][0] == "info"
    assert "hello world" in calls[0][1]
    assert "<" in calls[0][1] and ">1" in calls[0][1]


def test_process_message_invalid_json_logs_warning(monkeypatch):
    """
    Invalid JSON payloads should be reported as warning logs.
    """

    calls = []

    class DummyLogger:
        """
        Minimal logger double used to capture emitted log records.
        """

        def log(self, log_type, message, origin, include_timestamp=False):
            calls.append((log_type, message, origin))

        def close(self):
            """No-op close required by logger."""
            pass

    monkeypatch.setattr(log_server, "logger", DummyLogger())

    log_server._process_message("not valid json")

    assert len(calls) == 1
    assert calls[0][0] == "warning"


def test_logger_does_not_prepend_own_timestamp(monkeypatch, tmp_path):
    """
    The log server formatter should not add a server-side timestamp prefix.
    """

    monkeypatch.setattr(log_server, "LOGGER_NAME", "test-log-server-logger")

    log_file = tmp_path / "server.log"
    test_logger = log_server.Logger(str(log_file), logging.INFO, logging.INFO)
    test_logger.log("info", "payload message", "origin")
    test_logger.close()

    line = log_file.read_text(encoding="utf-8").strip()

    assert line.startswith("INFO - [origin] payload message")
    assert "," not in line.split(" - ", 1)[0]


def test_logger_can_prepend_timestamp_for_server_events(monkeypatch, tmp_path):
    """
    Server-generated logs should keep a timestamp prefix.
    """

    monkeypatch.setattr(log_server, "LOGGER_NAME", "test-log-server-logger-ts")

    log_file = tmp_path / "server-ts.log"
    test_logger = log_server.Logger(str(log_file), logging.INFO, logging.INFO)
    test_logger.log("info", "server event", "origin", include_timestamp=True)
    test_logger.close()

    line = log_file.read_text(encoding="utf-8").strip()
    prefix, rest = line.split(" - ", 1)

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}", prefix)
    assert rest == "INFO - [origin] server event"
