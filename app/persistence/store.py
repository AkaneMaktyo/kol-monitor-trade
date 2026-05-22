"""MySQL 日志存储。"""

import pymysql
from pymysql.cursors import DictCursor

from app.config import MySQLConfig
from app.models import LogEntry, LogLevel, Platform


class LogStore:
    def __init__(self, config: MySQLConfig):
        self._config = config

    def initialize(self) -> None:
        database = self._quoted_database()
        with self._connect(use_database=False) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS {database} "
                    f"CHARACTER SET {self._config.charset} COLLATE {self._collation()}"
                )
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(self._create_table_sql())

    def save(self, entry: LogEntry) -> None:
        sql = """
            INSERT INTO log_entries (
                id, timestamp, level, platform, source_channel,
                target_channel, content, message_id, author,
                forwarded, error_message
            ) VALUES (
                %(id)s, %(timestamp)s, %(level)s, %(platform)s, %(source_channel)s,
                %(target_channel)s, %(content)s, %(message_id)s, %(author)s,
                %(forwarded)s, %(error_message)s
            )
            ON DUPLICATE KEY UPDATE
                timestamp=VALUES(timestamp),
                level=VALUES(level),
                platform=VALUES(platform),
                source_channel=VALUES(source_channel),
                target_channel=VALUES(target_channel),
                content=VALUES(content),
                message_id=VALUES(message_id),
                author=VALUES(author),
                forwarded=VALUES(forwarded),
                error_message=VALUES(error_message)
        """
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, self._serialize(entry))

    def exists_message(self, platform: str, message_id: str) -> bool:
        if not message_id:
            return False
        sql = "SELECT id FROM log_entries WHERE platform=%s AND message_id=%s LIMIT 1"
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (platform, message_id))
                return cursor.fetchone() is not None

    def exists_content_link(self, platform: str, link: str) -> bool:
        if not link:
            return False
        sql = "SELECT id FROM log_entries WHERE platform=%s AND content LIKE %s LIMIT 1"
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (platform, f"%{link}%"))
                return cursor.fetchone() is not None

    def list_logs(self, limit: int = 50, level: str = "", platform: str = "") -> list[dict]:
        limit = max(1, min(limit, 500))
        where, params = self._filters(level, platform)
        sql = f"SELECT * FROM log_entries {where} ORDER BY timestamp DESC LIMIT %s"
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, [*params, limit])
                rows = cursor.fetchall()
        return [self._row_dict(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM log_entries")
                row = cursor.fetchone()
        return int(row["total"])

    def hydrate_recent(self, limit: int = 50) -> list[LogEntry]:
        rows = reversed(self.list_logs(limit=limit))
        return [self._to_entry(row) for row in rows]

    def _connect(self, use_database: bool = True):
        return pymysql.connect(
            host=self._config.host,
            port=self._config.port,
            user=self._config.user,
            password=self._config.password,
            database=self._config.database if use_database else None,
            charset=self._config.charset,
            autocommit=True,
            cursorclass=DictCursor,
        )

    def _quoted_database(self) -> str:
        return f"`{self._config.database.replace('`', '``')}`"

    def _collation(self) -> str:
        return "utf8mb4_unicode_ci" if self._config.charset == "utf8mb4" else "utf8_general_ci"

    @staticmethod
    def _create_table_sql() -> str:
        return """
            CREATE TABLE IF NOT EXISTS log_entries (
                id VARCHAR(80) PRIMARY KEY,
                timestamp VARCHAR(32) NOT NULL,
                level VARCHAR(16) NOT NULL,
                platform VARCHAR(16) NOT NULL,
                source_channel VARCHAR(255),
                target_channel VARCHAR(255),
                content TEXT NOT NULL,
                message_id VARCHAR(255),
                author VARCHAR(255),
                forwarded TINYINT(1) NOT NULL DEFAULT 0,
                error_message TEXT,
                INDEX idx_logs_time (timestamp),
                INDEX idx_logs_level (level),
                INDEX idx_logs_platform (platform)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """

    @staticmethod
    def _filters(level: str, platform: str) -> tuple[str, list[str]]:
        clauses, params = [], []
        if level:
            clauses.append("level = %s")
            params.append(level)
        if platform:
            clauses.append("platform = %s")
            params.append(platform)
        return ("WHERE " + " AND ".join(clauses), params) if clauses else ("", params)

    @staticmethod
    def _serialize(entry: LogEntry) -> dict:
        data = entry.to_dict()
        data["forwarded"] = 1 if entry.forwarded else 0
        return data

    @staticmethod
    def _row_dict(row: dict) -> dict:
        data = dict(row)
        data["forwarded"] = bool(data["forwarded"])
        return data

    @staticmethod
    def _to_entry(row: dict) -> LogEntry:
        return LogEntry(
            id=row["id"],
            timestamp=row["timestamp"],
            level=LogLevel(row["level"]),
            platform=Platform(row["platform"]),
            source_channel=row["source_channel"] or "",
            target_channel=row["target_channel"] or "",
            content=row["content"],
            message_id=row["message_id"] or "",
            author=row["author"] or "",
            forwarded=bool(row["forwarded"]),
            error_message=row["error_message"] or "",
        )
