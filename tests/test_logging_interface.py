"""
Regression tests for the SQLite UDP logging interface.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

import logging_interface
from pathlib import Path
import pytest


def _create_backlog_database(db_path):
    """
    Create a small SQLite backlog database with one unsent log entry.
    """

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                service TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                tags TEXT,
                sent INTEGER DEFAULT 0,
                attempts INTEGER DEFAULT 0,
                last_attempt TEXT
            )
            """)
        conn.execute("""
            CREATE TABLE log_stats (
                date TEXT PRIMARY KEY,
                total INTEGER DEFAULT 0,
                sent INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0
            )
            """)

        conn.execute(
            """
            INSERT INTO logs (timestamp, service, level, message, tags)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "2026-05-01 12:00:00",
                "old-service",
                "INFO",
                "backlog message",
                None,
            ),
        )
        conn.execute(
            "INSERT INTO log_stats (date, total, sent, failed) VALUES (?, ?, ?, ?)",
            ("2026-05-01", 1, 0, 0),
        )


def test_old_database_is_drained_deleted_and_merged(tmp_path, monkeypatch):
    """
    Old SQLite backlog databases should be drained and removed once empty.
    """

    monkeypatch.setattr(
        logging_interface,
        "__file__",
        str(tmp_path / "logging_interface.py"),
    )

    logger = logging_interface.SQLiteUDPLogger(
        syslog_host="localhost",
        syslog_port=514,
        service_name="test-service",
        db_filename="active.db",
        max_retries=5,
        retry_delay=1,
    )
    logger.socket = SimpleNamespace(
        sendto=lambda *args, **kwargs: None,
        close=lambda: None,
    )

    old_db_path = logger.logs_dir / "2026-05-01_00-00-00-test-service-log.db"
    _create_backlog_database(old_db_path)

    unsent_logs = logger._get_unsent_logs(old_db_path)
    assert len(unsent_logs) == 1

    log_id, timestamp, level, message, tags, _attempts = unsent_logs[0]
    assert logger._send_to_syslog(old_db_path, log_id, timestamp, level, message, tags)

    logger._cleanup_database_file(old_db_path)

    assert not old_db_path.exists()
    stats = logger.get_stats()
    assert stats["total"] == 1
    assert stats["sent"] == 1
    assert stats["pending"] == 0


def _logs_dir() -> Path:
    return Path(__file__).parent.parent / "logs"


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except Exception:
        pass


def test_send_updates_stats_and_deletes_row():
    logs_dir = _logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)

    db_name = "test_send.db"
    logger = logging_interface.SQLiteUDPLogger(
        syslog_host="127.0.0.1", syslog_port=514, db_filename=db_name
    )

    # Replace socket.sendto with a no-op to avoid network
    logger.socket = SimpleNamespace(sendto=lambda data, addr: None)

    # Insert a log entry using public API
    log_id = logger.log("hello world", level="INFO")
    assert isinstance(log_id, int)

    # Fetch unsent logs and send one
    unsent = logger._get_unsent_logs(logger.db_path)
    assert len(unsent) >= 1

    lid, ts, lvl, msg, tags, attempts = unsent[0]
    sent_ok = logger._send_to_syslog(logger.db_path, lid, ts, lvl, msg, tags)
    assert sent_ok is True

    # Row should be deleted now
    with logger._get_connection(logger.db_path) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM logs WHERE id = ?", (lid,))
        assert cur.fetchone()[0] == 0

    # Stats should have an incremented sent value for the date
    date = ts[:10]
    with logger._get_connection(logger.db_path) as conn:
        cur = conn.execute("SELECT sent, total FROM log_stats WHERE date = ?", (date,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] >= 1

    _remove_file(logger.db_path)


def test_recovery_merges_stats_and_deletes_old_db():
    logs_dir = _logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)

    active_db = logs_dir / "test_active.db"
    old_db = logs_dir / "test_old.db"

    # Ensure clean state
    _remove_file(active_db)
    _remove_file(old_db)

    # Create an 'old' DB and populate schema and data
    conn = sqlite3.connect(old_db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            service TEXT,
            level TEXT,
            message TEXT,
            tags TEXT,
            sent INTEGER DEFAULT 0,
            attempts INTEGER DEFAULT 0,
            last_attempt TEXT
        )
        """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS log_stats (
            date TEXT PRIMARY KEY,
            total INTEGER DEFAULT 0,
            sent INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0
        )
        """)

    # Insert a log and a stats row
    ts = "2026-05-05 12:00:00"
    conn.execute(
        "INSERT INTO logs (timestamp, service, level, message) VALUES (?, ?, ?, ?)",
        (ts, "svc", "INFO", "old log"),
    )
    conn.execute(
        "INSERT OR REPLACE INTO log_stats (date, total, sent, failed) VALUES (?, ?, ?, ?)",
        (ts[:10], 1, 0, 0),
    )
    conn.commit()
    conn.close()

    # Create active logger which will absorb stats
    logger = logging_interface.SQLiteUDPLogger(
        syslog_host="127.0.0.1", syslog_port=514, db_filename=active_db.name
    )
    logger.socket = SimpleNamespace(sendto=lambda data, addr: None)

    # Drain unsent logs from old DB
    unsent = logger._get_unsent_logs(old_db)
    assert len(unsent) == 1
    lid, ts2, lvl, msg, tags, attempts = unsent[0]
    assert ts2.startswith("2026-05-05")

    ok = logger._send_to_syslog(old_db, lid, ts2, lvl, msg, tags)
    assert ok is True

    # Now merge stats and cleanup
    logger._cleanup_database_file(old_db)

    # Old DB should be deleted
    assert not old_db.exists()

    # Active DB must contain the merged stats
    with logger._get_connection() as conn:
        cur = conn.execute("SELECT total FROM log_stats WHERE date = ?", (ts2[:10],))
        row = cur.fetchone()
        assert row is not None and row[0] >= 1

    _remove_file(logger.db_path)


def test_unlink_retry_on_permission_error(monkeypatch):
    logs_dir = _logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)

    old_db = logs_dir / "test_retry.db"
    _remove_file(old_db)

    # create a minimal DB
    conn = sqlite3.connect(old_db)
    conn.execute("CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS log_stats (date TEXT PRIMARY KEY, total INTEGER DEFAULT 0, sent INTEGER DEFAULT 0, failed INTEGER DEFAULT 0)"
    )
    conn.commit()
    conn.close()

    logger = logging_interface.SQLiteUDPLogger(
        syslog_host="127.0.0.1", syslog_port=514, db_filename="test_active_retry.db"
    )

    # Track unlink attempts for this path
    attempts = {old_db.name: 0}

    real_unlink = Path.unlink

    def fake_unlink(self, missing_ok=False):
        if self.name == old_db.name and attempts[old_db.name] < 2:
            attempts[old_db.name] += 1
            raise PermissionError("simulated lock")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fake_unlink)

    # Ensure no rows so cleanup will try to delete
    logger._cleanup_database_file(old_db)

    # After cleanup, file should be gone
    assert not old_db.exists()

    # restore and cleanup active DB
    monkeypatch.setattr(Path, "unlink", real_unlink)
    _remove_file(logger.db_path)
