"""
Complete SQLite-based logger with UDP syslog forwarding.
Aimed at production use in very low-volume architectures.
"""

# Standard library imports
import sqlite3
import json
import socket
import threading
import time
from contextlib import contextmanager as contextlib_contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List


class SQLiteUDPLogger:
    """
    Production-ready logger for low-volume systems.
    Logs are stored in SQLite, with background thread sending to syslog.
    """

    def __init__(
        self,
        syslog_host: str,
        service_name: str = "unknown-service",  # name of the service using the interface object
        syslog_port: int = 514,  # standard syslog UDP port as default
        db_filename: str = "",  # filename for SQLite database file
        max_retries: int = 5,  # max number of retries to send a log message via UDP
        retry_delay: int = 30,  # delay between retries in seconds
    ):

        self.syslog_host = syslog_host
        self.syslog_port = syslog_port
        self.service_name = service_name
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # If no explicit DB path, create one with timestamp and service name
        # Couldn't be in default params because datetime.utcnow() needs to be called at init time and service_name is needed
        if db_filename == "":
            db_filename = f"{datetime.utcnow().strftime('%Y-%m-d_%H-%M-%S')}-{self.service_name}-log.db"

        # TODO: fix deprecated usage of datetime.utcnow()

        # Always create in idranti-sicuri-logs subdirectory
        current_dir = Path(__file__).parent.absolute()
        logs_dir = current_dir / "idranti-sicuri-logs"

        # Create directory if it doesn't exist
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Create full path to database file
        self.db_path = logs_dir / db_filename
        db_path_obj = Path(self.db_path)
        db_path_obj.touch(exist_ok=True)  # Ensure file exists
        self._init_database()  # Initialize DB schema

        # Background thread for sending logs
        self.sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self.running = False  # Control flag for thread

        # UDP socket (reused)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Statistics
        self.stats = {"sent": 0, "failed": 0, "pending": 0}

    def _init_database(self):
        """Initialize SQLite database with proper schema"""

        with self._get_connection() as conn:

            # Main logs table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    service TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    tags TEXT,
                    message_id TEXT,
                    
                    -- Delivery tracking
                    sent INTEGER DEFAULT 0,
                    sent_at TEXT,
                    attempts INTEGER DEFAULT 0,
                    last_attempt TEXT,
                    error_message TEXT,
                    
                    -- For batching/prioritization
                    priority INTEGER DEFAULT 0, -- 0=normal, 1=high, 2=critical
                    
                    -- Indexes for performance
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create indexes for efficient querying of unsent logs and stats
            conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_sent ON logs(sent)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_priority ON logs(priority, sent)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)"
            )

            # Statistics table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS log_stats (
                    date TEXT PRIMARY KEY,
                    total INTEGER DEFAULT 0,
                    sent INTEGER DEFAULT 0,
                    failed INTEGER DEFAULT 0
                )
            """
            )

    @property
    def _connection(self):
        """Thread-safe SQLite connection"""
        # SQLite handles thread safety with check_same_thread=False
        return sqlite3.connect(self.db_path, check_same_thread=False)

    @contextlib_contextmanager
    def _get_connection(self):
        """Context manager for database connection"""
        conn = self._connection
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _get_current_utc_time(self) -> datetime:
        """Get current UTC time as datetime object"""
        return datetime.utcnow()

    def _format_datetime_utc(self, dt: datetime) -> str:
        """Format datetime as UTC string without timezone (YYYY-MM-DD HH:MM:SS)"""
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def log(
        self,
        message: str,
        level: str = "INFO",
        sd_tags: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None,
        priority: int = 0,
    ) -> int:
        """
        Store a log message in SQLite.
        message: log message text
        level: log level (e.g., INFO, ERROR)
        sd_tags: optional dictionary of that will form part of the structured data
        source: optional source identifier (e.g., module name)
        priority: integer priority (0=normal, 1=high, 2=critical)

        N.B: The service identifier is added by the logging interface itself (so no need to pass the value in the tags).

        Returns the log ID in the SQLite database.
        """
        # Get current UTC time
        current_time = self._get_current_utc_time()

        log_entry = {
            "timestamp": self._format_datetime_utc(current_time),
            "service": self.service_name,
            "level": level,
            "message": message,
            "message_id": message_id,
            "tags": json.dumps(sd_tags) if sd_tags else None,
            "priority": priority,
        }

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO logs 
                (timestamp, service, level, message, tags, source, priority)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    log_entry["timestamp"],
                    log_entry["service"],
                    log_entry["level"],
                    log_entry["message"],
                    log_entry["tags"],
                    log_entry["priority"],
                ),
            )

            log_id = cursor.lastrowid  # Get the ID of the inserted log for tracking
            print(
                f"(Logging interface) Passing log message #{log_id}: {message[:50]}..."
            )

            # Update daily stats - use UTC date
            today = current_time.strftime("%Y-%m-%d")
            conn.execute(
                """
                INSERT OR IGNORE INTO log_stats (date) VALUES (?)
            """,
                (today,),
            )
            conn.execute(
                """
                UPDATE log_stats 
                SET total = total + 1 
                WHERE date = ?
            """,
                (today,),
            )

        return log_id

    def _get_unsent_logs(self, batch_size: int = 10) -> List[tuple]:
        """
        Retrieves logs that haven't been sent yet

        batch_size: number of logs to retrieve at once

        Returns a list of log tuples
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, timestamp, level, message, tags, attempts
                FROM logs 
                WHERE sent = 0 
                AND (attempts < ? OR last_attempt < ?)
                ORDER BY priority DESC, timestamp ASC
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
        log_id: int,
        timestamp: str,
        level: str,
        message: str,
        tags_str: Optional[str],
    ) -> bool:
        """Send a single log to syslog via UDP"""
        try:
            # Parse tags
            tags = json.loads(tags_str) if tags_str else {}

            # Create a simple data structure with the log information
            log_data = {
                "timestamp": timestamp,
                "level": level,
                "message": message,
                "tags": tags,
                "service": self.service_name,
                "hostname": socket.gethostname(),
            }

            # Convert to JSON for transmission
            json_data = json.dumps(log_data)

            # Send via UDP
            self.socket.sendto(
                json_data.encode("utf-8"), (self.syslog_host, self.syslog_port)
            )

            # Mark as sent
            current_utc = self._get_current_utc_time()
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE logs 
                    SET sent = 1, 
                        sent_at = ?,
                        attempts = attempts + 1,
                        last_attempt = ?
                    WHERE id = ?
                """,
                    (
                        self._format_datetime_utc(current_utc),
                        self._format_datetime_utc(current_utc),
                        log_id,
                    ),
                )

                # Update stats
                today = current_utc.strftime("%Y-%m-%d")
                conn.execute(
                    """
                    UPDATE log_stats 
                    SET sent = sent + 1 
                    WHERE date = ?
                """,
                    (today,),
                )

            self.stats["sent"] += 1
            return True

        except Exception as ex:
            # Record failure
            current_utc = self._get_current_utc_time()
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE logs 
                    SET attempts = attempts + 1,
                        last_attempt = ?,
                        error_message = ?
                    WHERE id = ?
                """,
                    (
                        self._format_datetime_utc(current_utc),
                        str(ex)[:500],  # Truncate long errors
                        log_id,
                    ),
                )

                # Update stats
                today = current_utc.strftime("%Y-%m-%d")
                conn.execute(
                    """
                    UPDATE log_stats 
                    SET failed = failed + 1 
                    WHERE date = ?
                """,
                    (today,),
                )

            self.stats["failed"] += 1
            print(f"Failed to send log with id {log_id}: {ex}")
            return False

    def _sender_loop(self):
        """
        Background thread that sends unsent logs.
        """
        print(f"Log sender thread started for service {self.service_name}")

        while self.running:
            try:
                # Get unsent logs
                unsent_logs = self._get_unsent_logs()

                if unsent_logs:
                    print(
                        f"Logging background thread found {len(unsent_logs)} unsent logs"
                    )

                    # Send each log
                    for log in unsent_logs:
                        log_id, timestamp, level, message, tags, attempts = log

                        success = self._send_to_syslog(
                            log_id, timestamp, level, message, tags
                        )

                        # Small delay between sends (optional)
                        time.sleep(0.1)

                # Update pending count
                with self._get_connection() as conn:
                    cursor = conn.execute("SELECT COUNT(*) FROM logs WHERE sent = 0")
                    self.stats["pending"] = cursor.fetchone()[0]

                # Wait before next check (longer if nothing to send)
                sleep_time = 5 if unsent_logs else self.retry_delay
                time.sleep(sleep_time)

            except Exception as ex:
                print(f"Error in sender loop: {ex}")
                time.sleep(30)  # Wait half a minute on error to avoid tight loops

    def start(self):
        """Start the background sender thread"""
        self.running = True
        self.sender_thread.start()
        print(
            f"Logger started for {self.service_name}, sending to {self.syslog_host}:{self.syslog_port}"
        )

    def stop(self):
        """Graceful shutdown"""
        print("Stopping logger...")
        self.running = False
        self.sender_thread.join(timeout=10)
        self.socket.close()
        print("Logger stopped")

    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        current_utc = self._get_current_utc_time()
        one_week_ago = self._format_datetime_utc(current_utc - timedelta(days=7))

        with self._get_connection() as conn:
            # Get counts
            cursor = conn.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN sent = 1 THEN 1 ELSE 0 END) as sent,
                    SUM(CASE WHEN sent = 0 AND attempts >= ? THEN 1 ELSE 0 END) as failed_permanently,
                    SUM(CASE WHEN sent = 0 AND attempts < ? THEN 1 ELSE 0 END) as pending
                FROM logs
                WHERE timestamp > ?
            """,
                (
                    self.max_retries,
                    self.max_retries,
                    one_week_ago,
                ),
            )

            row = cursor.fetchone()

            # Get recent failures
            cursor = conn.execute(
                """
                SELECT message, error_message, attempts, timestamp
                FROM logs
                WHERE sent = 0 AND attempts > 0
                ORDER BY last_attempt DESC
                LIMIT 5
            """
            )
            recent_failures = cursor.fetchall()

        return {
            "total": row[0] or 0,
            "sent": row[1] or 0,
            "pending": row[3] or 0,
            "permanently_failed": row[2] or 0,
            "recent_failures": recent_failures,
            "service": self.service_name,
            "syslog_target": f"{self.syslog_host}:{self.syslog_port}",
        }

    def clear_sent_logs_before(self, before_timestamp: datetime) -> int:
        """
        Delete all logs marked as sent (sent=1) with timestamp before the given datetime.
        Returns the number of deleted rows.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM logs
                WHERE sent = 1 AND timestamp < ?
                """,
                (self._format_datetime_utc(before_timestamp),),
            )
            deleted = cursor.rowcount
        return deleted

    def query_logs(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        level: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Query logs with filters"""

        query = "SELECT * FROM logs WHERE 1=1"
        params = []

        if since:
            query += " AND timestamp >= ?"
            params.append(self._format_datetime_utc(since))

        if until:
            query += " AND timestamp <= ?"
            params.append(self._format_datetime_utc(until))

        if level:
            query += " AND level = ?"
            params.append(level)

        if source:
            query += " AND source = ?"
            params.append(source)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            # Get column names
            column_names = [desc[0] for desc in cursor.description]

            # Convert to dicts
            results = []
            for row in rows:
                log_dict = dict(zip(column_names, row))
                if log_dict.get("tags"):
                    log_dict["tags"] = json.loads(log_dict["tags"])
                results.append(log_dict)

            return results


# Factory function for easy integration
def create_interface(
    syslog_host,
    syslog_port=None,
    service_name=None,
    max_retries=None,
    retry_delay=None,
    db_filename=None,
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
