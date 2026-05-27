"""LLM 解析提示词配置存储。"""

import unicodedata
import uuid

from app.config import MySQLConfig
from app.models import app_now
from app.persistence import connect_mysql


class PromptProfileStore:
    def __init__(self, config: MySQLConfig):
        self._config = config

    def initialize(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(self._create_table_sql())

    def list_profiles(self) -> list[dict]:
        sql = """
            SELECT * FROM signal_prompt_profiles
            ORDER BY enabled DESC, updated_at DESC, name ASC
        """
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
        return [self._row_dict(row) for row in rows]

    def get(self, profile_id: str) -> dict | None:
        sql = "SELECT * FROM signal_prompt_profiles WHERE id=%s LIMIT 1"
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (profile_id,))
                row = cursor.fetchone()
        return self._row_dict(row) if row else None

    def save(self, data: dict) -> dict:
        now = app_now()
        profile_id = data.get("id") or f"prompt_{uuid.uuid4().hex}"
        existing = self.get(profile_id)
        payload = {
            "id": profile_id,
            "name": data["name"].strip(),
            "source_author": data.get("source_author", "").strip(),
            "source_channel": data.get("source_channel", "").strip(),
            "prompt": data["prompt"].strip(),
            "enabled": 1 if data.get("enabled", True) else 0,
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
        }
        sql = """
            INSERT INTO signal_prompt_profiles (
                id, name, source_author, source_channel, prompt,
                enabled, created_at, updated_at
            ) VALUES (
                %(id)s, %(name)s, %(source_author)s, %(source_channel)s, %(prompt)s,
                %(enabled)s, %(created_at)s, %(updated_at)s
            )
            ON DUPLICATE KEY UPDATE
                name=VALUES(name),
                source_author=VALUES(source_author),
                source_channel=VALUES(source_channel),
                prompt=VALUES(prompt),
                enabled=VALUES(enabled),
                updated_at=VALUES(updated_at)
        """
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, payload)
        return self.get(profile_id) or payload

    def delete(self, profile_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM signal_prompt_profiles WHERE id=%s",
                    (profile_id,),
                )
                return cursor.rowcount > 0

    def best_match(self, author: str, channel: str) -> dict | None:
        author = author.strip()
        channel = channel.strip()
        matches = []
        for profile in self.list_profiles():
            if not profile["enabled"]:
                continue
            author_ok = self._match(profile["source_author"], author)
            channel_ok = self._match(profile["source_channel"], channel)
            if author_ok and channel_ok:
                score = int(bool(profile["source_author"])) * 2
                score += int(bool(profile["source_channel"]))
                matches.append((score, profile))
        return max(matches, key=lambda item: item[0])[1] if matches else None

    @staticmethod
    def _match(pattern: str, value: str) -> bool:
        pattern = unicodedata.normalize("NFKC", pattern.strip()).lower()
        value = unicodedata.normalize("NFKC", value.strip()).lower()
        if not pattern:
            return True
        return bool(value and (pattern in value or value in pattern))

    def _connect(self):
        return connect_mysql(self._config)

    @staticmethod
    def _create_table_sql() -> str:
        return """
            CREATE TABLE IF NOT EXISTS signal_prompt_profiles (
                id VARCHAR(80) PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                source_author VARCHAR(255) NOT NULL DEFAULT '',
                source_channel VARCHAR(255) NOT NULL DEFAULT '',
                prompt TEXT NOT NULL,
                enabled TINYINT(1) NOT NULL DEFAULT 1,
                created_at VARCHAR(32) NOT NULL,
                updated_at VARCHAR(32) NOT NULL,
                INDEX idx_prompt_enabled (enabled),
                INDEX idx_prompt_author (source_author),
                INDEX idx_prompt_channel (source_channel)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """

    @staticmethod
    def _row_dict(row: dict) -> dict:
        data = dict(row)
        data["enabled"] = bool(data["enabled"])
        return data
