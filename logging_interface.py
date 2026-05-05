"""
SQLite + UDP syslog logger with backlog recovery

This module implements a lightweight production-ready logging interface
designed for low-volume services. It stores log rows in per-service
SQLite files under a `logs/` directory and forwards them to a syslog
receiver over UDP.

Key features
- Persistent on-disk write-ahead (SQLite files) so logs are not lost when
    the network or receiver is unavailable.
- Two cooperating background threads:
    - sender thread: continuously drains and forwards logs from the *active*
        database file used by the running service.
    - recovery thread: runs independently to discover and drain older backlog
        database files in `logs/` so they can be removed after their rows are
        forwarded.

Thread lifecycle summary
- Both threads are created as daemon threads in `SQLiteUDPLogger.__init__`
    and started together by calling `start()`; shutting down is done with
    `stop()` which clears the `running` flag and joins both threads.
- The sender thread focuses solely on the active DB: it queries unsent
    rows, sends them via UDP, updates per-day stats, and deletes rows once
    acknowledged.
- The recovery thread iterates over other `.db` files (older backlogs). For
    each file it finds unsent rows, forwards them, merges the source file's
    per-day stats into the active DB, and deletes the old file when it is
    empty. Deletion includes a short retry loop and an explicit `gc.collect()`
    to avoid file-lock issues from lingering SQLite handles.

Design notes
- Daily statistics (`log_stats`) are merged into the active database before
    an old file is removed. This preserves historical counts without a
    separate central store.
- The whole module assumes low message volume; if you expect heavy write
    rates, consider a higher-performance pipeline (buffered sockets, a
    message queue, or a dedicated logging service).

"""

# Standard library imports
import gc  # Garbage collection manual control (force a collection cycle to unlock files before deletion)
import sqlite3
import socket
import threading
from json import loads as json_loads
from json import dumps as json_dumps
from time import sleep as time_sleep
from contextlib import contextmanager as contextlib_contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List


class SQLiteUDPLogger:
    """
    Production-ready logger for low-volume systems.

    Public API (start/stop/log/query/get_stats) comes first, followed by
    background thread run loops, then internal helpers and database helpers.
    This ordering is deliberate to make the class easier to scan and
    reason about while preserving existing runtime behavior.
    """

    # -- Public API -------------------------------------------------
    def __init__(
        self,
        syslog_host: str,
        service_name: str = "unknown-service",
        syslog_port: int = 514,
        db_filename: str = "",
        max_retries: int = 5,
        retry_delay: int = 3,
    ):
        self.syslog_host = syslog_host
        self.syslog_port = syslog_port
        self.service_name = service_name
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        if db_filename == "":
            db_filename = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S')}-{self.service_name}-log.db"

        current_dir = Path(__file__).parent.absolute()
        self.logs_dir = current_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.logs_dir / db_filename
        Path(self.db_path).touch(exist_ok=True)
        self._init_database()

        # Threads are created once and started/stopped via start()/stop()
        self.sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self.recovery_thread = threading.Thread(target=self._recovery_loop, daemon=True)
        self.running = False

        # Reused UDP socket for sending log JSON to syslog target
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Lightweight in-memory counters for quick introspection
        self.stats = {"sent": 0, "failed": 0, "pending": 0}

    def start(self) -> None:
        """Start sender and recovery background threads."""

        self.running = True
        self.sender_thread.start()
        self.recovery_thread.start()

        print(
            f"Log interface started for {self.service_name}, sending to {self.syslog_host}:{self.syslog_port}"
        )

    def stop(self) -> None:
        """Gracefully stop background threads and release resources."""

        print("Stopping log interface...")
        self.running = False
        self.sender_thread.join(timeout=10)
        self.recovery_thread.join(timeout=10)
        try:
            self.socket.close()
        except Exception:
            pass
        print("Log interface stopped")

    def log(
        self,
        message: str,
        level: str = "INFO",
        sd_tags: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None,
        source: Optional[str] = None,
    ) -> int | None:
        """Store a log message in the active SQLite database and update daily stats."""

        current_time = self._get_current_utc_time()
        timestamp = self._format_datetime_utc(current_time)

        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO logs (timestamp, service, level, message, tags)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp,
                        self.service_name,
                        level,
                        message,
                        json_dumps(sd_tags) if sd_tags else None,
                    ),
                )

                log_id = cursor.lastrowid

                today = current_time.strftime("%Y-%m-%d")
                conn.execute(
                    "INSERT OR IGNORE INTO log_stats (date) VALUES (?)", (today,)
                )
                conn.execute(
                    "UPDATE log_stats SET total = total + 1 WHERE date = ?", (today,)
                )

        except sqlite3.OperationalError as op_ex:
            # If the DB schema wasn't created for some reason (rare in tests
            # that dynamically manipulate files), ensure schema exists and retry once.
            if "no such table" in str(op_ex).lower():
                try:
                    self._init_database()
                    with self._get_connection() as conn:
                        cursor = conn.execute(
                            """
                            INSERT INTO logs (timestamp, service, level, message, tags)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                timestamp,
                                self.service_name,
                                level,
                                message,
                                json_dumps(sd_tags) if sd_tags else None,
                            ),
                        )

                        log_id = cursor.lastrowid
                        today = current_time.strftime("%Y-%m-%d")
                        conn.execute(
                            "INSERT OR IGNORE INTO log_stats (date) VALUES (?)",
                            (today,),
                        )
                        conn.execute(
                            "UPDATE log_stats SET total = total + 1 WHERE date = ?",
                            (today,),
                        )
                except Exception:
                    raise
            else:
                raise

        print(f"(Logging interface) Passing log message #{log_id}: {message[:50]}...")
        return log_id

    def query_logs(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        level: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query stored logs with simple filters and return a list of dicts."""

        query = "SELECT * FROM logs WHERE 1=1"
        params: list[str | int] = []

        if since:
            query += " AND timestamp >= ?"
            params.append(self._format_datetime_utc(since))

        if until:
            query += " AND timestamp <= ?"
            params.append(self._format_datetime_utc(until))

        if level:
            query += " AND level = ?"
            params.append(level)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            column_names: list[str] = [desc[0] for desc in cursor.description]

            results: list[dict[str, Any]] = []
            for row in rows:
                log_dict = dict(zip(column_names, row))
                if log_dict.get("tags"):
                    log_dict["tags"] = json_loads(log_dict["tags"])
                results.append(log_dict)

            return results

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregated stats across all database files (last 7 days)."""

        current_utc = self._get_current_utc_time()
        one_week_ago = self._format_datetime_utc(current_utc - timedelta(days=7))

        total = sent = failed = pending = permanently_failed = 0
        recent_failures: list[tuple[str, int, str, Optional[str]]] = []

        for db_path in self._get_database_files():
            if not db_path.exists():
                continue

            with self._get_connection(db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT COALESCE(SUM(total), 0), COALESCE(SUM(sent), 0), COALESCE(SUM(failed), 0)
                    FROM log_stats WHERE date > ?
                    """,
                    (one_week_ago,),
                )
                row = cursor.fetchone()
                total += row[0] or 0
                sent += row[1] or 0
                failed += row[2] or 0

                cursor = conn.execute(
                    """
                    SELECT SUM(CASE WHEN attempts >= ? THEN 1 ELSE 0 END),
                           SUM(CASE WHEN attempts < ? THEN 1 ELSE 0 END)
                    FROM logs WHERE timestamp > ?
                    """,
                    (self.max_retries, self.max_retries, one_week_ago),
                )
                log_row = cursor.fetchone()
                permanently_failed += log_row[0] or 0
                pending += log_row[1] or 0

                cursor = conn.execute("""
                    SELECT message, attempts, timestamp, last_attempt
                    FROM logs WHERE sent = 0 AND attempts > 0
                    ORDER BY last_attempt DESC LIMIT 5
                    """)
                recent_failures.extend(cursor.fetchall())

        recent_failures = sorted(
            recent_failures, key=lambda r: r[3] or "", reverse=True
        )[:5]

        return {
            "total": total,
            "sent": sent,
            "pending": pending,
            "permanently_failed": permanently_failed,
            "recent_failures": recent_failures,
            "service": self.service_name,
            "syslog_target": f"{self.syslog_host}:{self.syslog_port}",
        }

    def clear_sent_logs_before(self, before_timestamp: datetime) -> int:
        """Delete sent logs older than `before_timestamp` and return deleted count."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM logs WHERE sent = 1 AND timestamp < ?",
                (self._format_datetime_utc(before_timestamp),),
            )
            return cursor.rowcount

    # -- Background threads -----------------------------------------
    def _sender_loop(self) -> None:
        """Continuously send unsent logs from the active database."""

        print(f"Log sender thread started for service {self.service_name}")

        while self.running:
            try:
                active_unsent_logs = self._get_unsent_logs(self.db_path)

                if active_unsent_logs:
                    print(
                        f"Logging background thread found {len(active_unsent_logs)} unsent logs in {self.db_path.name}"
                    )
                    for log in active_unsent_logs:
                        log_id, timestamp, level, message, tags, attempts = log
                        self._send_to_syslog(
                            self.db_path, log_id, timestamp, level, message, tags
                        )
                        time_sleep(0.1)

                with self._get_connection(self.db_path) as conn:
                    cursor = conn.execute("SELECT COUNT(*) FROM logs WHERE sent = 0")
                    self.stats["pending"] = cursor.fetchone()[0]

                sleep_time = 5 if active_unsent_logs else self.retry_delay
                time_sleep(sleep_time)

            except Exception as ex:
                print(f"Error in sender loop: {ex}")
                time_sleep(30)

    def _recovery_loop(self) -> None:
        """Discover and drain older backlog database files without blocking the sender."""

        print(f"Log recovery thread started for service {self.service_name}")

        while self.running:
            try:
                recovered_anything = False

                for db_path in self._get_database_files():
                    if db_path == self.db_path or not db_path.exists():
                        continue

                    unsent_logs = self._get_unsent_logs(db_path)
                    if unsent_logs:
                        recovered_anything = True
                        print(
                            f"Recovery thread found {len(unsent_logs)} unsent logs in {db_path.name}"
                        )
                        for log in unsent_logs:
                            log_id, timestamp, level, message, tags, _attempts = log
                            self._send_to_syslog(
                                db_path, log_id, timestamp, level, message, tags
                            )
                            time_sleep(0.1)

                    # Attempt to remove the file if it's empty and stats were merged
                    self._cleanup_database_file(db_path)

                if not recovered_anything:
                    time_sleep(self.retry_delay)

            except Exception as ex:
                print(f"Error in recovery loop: {ex}")
                time_sleep(30)

    # -- Internal helpers / DB operations ---------------------------
    def _init_database(self) -> None:
        """Create tables and indexes in the active database file."""

        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
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

            conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_sent ON logs(sent)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)"
            )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS log_stats (
                    date TEXT PRIMARY KEY,
                    total INTEGER DEFAULT 0,
                    sent INTEGER DEFAULT 0,
                    failed INTEGER DEFAULT 0
                )
                """)

    @contextlib_contextmanager
    def _get_connection(self, db_path: Optional[Path] = None):
        """Context manager yielding an sqlite3.Connection for the given DB path."""

        if db_path is None:
            db_path = self.db_path

        conn = sqlite3.connect(db_path, check_same_thread=False)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _get_current_utc_time(self) -> datetime:
        return datetime.now(timezone.utc)

    def _format_datetime_utc(self, dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _get_database_files(self) -> list[Path]:
        files = sorted(
            self.logs_dir.glob("*.db"), key=lambda p: (p.stat().st_mtime, p.name)
        )
        files = [p for p in files if p != self.db_path]
        files.append(self.db_path)
        return files

    def _database_has_pending_logs(self, db_path: Path) -> bool:
        with self._get_connection(db_path) as conn:
            cursor = conn.execute("SELECT 1 FROM logs LIMIT 1")
            return cursor.fetchone() is not None

    def _get_unsent_logs(
        self, db_path: Path, batch_size: int = 10
    ) -> list[tuple[int, str, str, str, Optional[str], int]]:
        with self._get_connection(db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, timestamp, level, message, tags, attempts
                FROM logs
                WHERE sent = 0 AND attempts < ? AND (attempts = 0 OR last_attempt < ?)
                ORDER BY CASE UPPER(level)
                    WHEN 'CRITICAL' THEN 3 WHEN 'ERROR' THEN 2 WHEN 'WARNING' THEN 1 ELSE 0 END DESC,
                timestamp ASC
                LIMIT ?
                """,
                (
                    self.max_retries,
                    self._format_datetime_utc(
                        self._get_current_utc_time() - timedelta(minutes=5)
                    ),
                    batch_size,
                ),
            )
            return cursor.fetchall()

    def _send_to_syslog(
        self,
        db_path: Path,
        log_id: int,
        timestamp: str,
        level: str,
        message: str,
        tags_str: Optional[str],
    ) -> bool:
        try:
            tags = json_loads(tags_str) if tags_str else {}
            log_data = {
                "timestamp": timestamp,
                "level": level,
                "message": message,
                "tags": tags,
                "service": self.service_name,
                "hostname": socket.gethostname(),
            }
            json_data = json_dumps(log_data)
            self.socket.sendto(
                json_data.encode("utf-8"), (self.syslog_host, self.syslog_port)
            )

            log_date = timestamp[:10]
            with self._get_connection(db_path) as conn:
                conn.execute("DELETE FROM logs WHERE id = ?", (log_id,))
                conn.execute(
                    "UPDATE log_stats SET sent = sent + 1 WHERE date = ?", (log_date,)
                )

            self.stats["sent"] += 1
            return True

        except Exception as ex:
            current_utc = self._get_current_utc_time()
            with self._get_connection(db_path) as conn:
                conn.execute(
                    "UPDATE logs SET attempts = attempts + 1, last_attempt = ? WHERE id = ?",
                    (self._format_datetime_utc(current_utc), log_id),
                )
                conn.execute(
                    "UPDATE log_stats SET failed = failed + 1 WHERE date = ?",
                    (timestamp[:10],),
                )

            self.stats["failed"] += 1
            print(f"Failed to send log with id {log_id}: {ex}")
            return False

    def _merge_log_stats_into_active_database(self, source_db_path: Path) -> None:
        """Merge per-day `log_stats` rows from `source_db_path` into the active DB.

        This function does not delete the source file; deletion is handled by
        `_cleanup_database_file` after verifying the source is empty.
        """
        if source_db_path == self.db_path:
            return

        with self._get_connection(source_db_path) as source_conn:
            rows = source_conn.execute(
                "SELECT date, total, sent, failed FROM log_stats"
            ).fetchall()

        if not rows:
            return

        with self._get_connection() as target_conn:
            for date_value, total, sent, failed in rows:
                target_conn.execute(
                    """
                    INSERT INTO log_stats (date, total, sent, failed) VALUES (?, ?, ?, ?)
                    ON CONFLICT(date) DO UPDATE SET
                        total = total + excluded.total,
                        sent = sent + excluded.sent,
                        failed = failed + excluded.failed
                    """,
                    (date_value, total or 0, sent or 0, failed or 0),
                )

    def _cleanup_database_file(self, db_path: Path) -> None:
        """If `db_path` is not the active DB and contains no rows, merge stats and remove file."""

        if db_path == self.db_path:
            return

        if not db_path.exists():
            return

        # If there are still rows, do nothing
        if self._database_has_pending_logs(db_path):
            return

        # Merge stats so counts are preserved
        try:
            self._merge_log_stats_into_active_database(db_path)
        except Exception as ex:
            print(f"Failed to merge stats from {db_path}: {ex}")
            return

        # Ensure any lingering file handles are released before attempting deletion
        gc.collect()

        for _attempt in range(8):
            try:
                db_path.unlink(missing_ok=True)
                break
            except PermissionError:
                time_sleep(0.1)
            except Exception as ex:
                print(f"Unexpected error deleting {db_path}: {ex}")
                break


# Factory function for easy integration
def create_interface(
    syslog_host: str,
    syslog_port: int,
    service_name: str,
    max_retries: int,
    retry_delay: int,
    db_filename: str,
) -> SQLiteUDPLogger:
    """
    Creates instance of logger interface with given configuration.
    """

    print("Attempting to create logging interface with:")
    print(f"syslog_host: {syslog_host}")
    print(f"syslog_port: {syslog_port}")
    print(f"service_name: {service_name}\n")

    # Defaults are already handled in SQLiteUDPLogger init
    return SQLiteUDPLogger(
        syslog_host=syslog_host,
        syslog_port=syslog_port,
        db_filename=db_filename,
        service_name=service_name,
        max_retries=max_retries,
        retry_delay=retry_delay,
    )
