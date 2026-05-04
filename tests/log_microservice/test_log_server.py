"""
Tests for log_server rate limiting and JSON message processing.
"""

import json
import importlib
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

        def log(self, log_type, message, origin):
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

        def log(self, log_type, message, origin):
            calls.append((log_type, message, origin))

        def close(self):
            """No-op close required by logger."""
            pass

    monkeypatch.setattr(log_server, "logger", DummyLogger())

    log_server._process_message("not valid json")

    assert len(calls) == 1
    assert calls[0][0] == "warning"
