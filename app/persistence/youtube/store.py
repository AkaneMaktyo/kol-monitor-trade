import json
from uuid import uuid4

from app.config import MySQLConfig
from app.persistence import connect_mysql
from app.persistence.youtube.schema import CHANNELS_SQL, VIDEOS_SQL


class YouTubeStore:
    def __init__(self, config: MySQLConfig):
        self._config = config

    def initialize(self) -> None:
        with connect_mysql(self._config, use_database=False) as conn:
            with conn.cursor() as cursor:
                cursor.execute(self._database_sql())
        with connect_mysql(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(CHANNELS_SQL)
                cursor.execute(VIDEOS_SQL)

    def list_channels(self) -> list[dict]:
        sql = "SELECT * FROM youtube_channels ORDER BY updated_at DESC"
        with connect_mysql(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                return [self._channel_row(row) for row in cursor.fetchall()]

    def get_channel(self, channel_row_id: str) -> dict | None:
        return self._one("SELECT * FROM youtube_channels WHERE id=%s LIMIT 1", (channel_row_id,), self._channel_row)

    def get_channel_by_remote_id(self, channel_id: str) -> dict | None:
        return self._one("SELECT * FROM youtube_channels WHERE channel_id=%s LIMIT 1", (channel_id,), self._channel_row)

    def save_channel(self, data: dict) -> dict:
        existing = self.get_channel_by_remote_id(data["channel_id"])
        payload = {
            "id": existing["id"] if existing else f"ytc_{uuid4().hex[:12]}",
            "channel_id": data["channel_id"],
            "title": data["title"],
            "handle": data.get("handle", ""),
            "source_url": data["source_url"],
            "enabled": 1 if data.get("enabled", True) else 0,
            "last_checked_at": data.get("last_checked_at", ""),
            "last_video_published_at": data.get("last_video_published_at", ""),
            "created_at": existing["created_at"] if existing else data["updated_at"],
            "updated_at": data["updated_at"],
        }
        sql = """
            INSERT INTO youtube_channels (
                id, channel_id, title, handle, source_url, enabled,
                last_checked_at, last_video_published_at, created_at, updated_at
            ) VALUES (
                %(id)s, %(channel_id)s, %(title)s, %(handle)s, %(source_url)s, %(enabled)s,
                %(last_checked_at)s, %(last_video_published_at)s, %(created_at)s, %(updated_at)s
            )
            ON DUPLICATE KEY UPDATE
                title=VALUES(title),
                handle=VALUES(handle),
                source_url=VALUES(source_url),
                enabled=VALUES(enabled),
                last_checked_at=VALUES(last_checked_at),
                last_video_published_at=VALUES(last_video_published_at),
                updated_at=VALUES(updated_at)
        """
        self._execute(sql, payload)
        return self.get_channel(payload["id"])

    def delete_channel(self, channel_row_id: str) -> bool:
        with connect_mysql(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM youtube_videos WHERE channel_row_id=%s", (channel_row_id,))
                deleted = cursor.execute("DELETE FROM youtube_channels WHERE id=%s", (channel_row_id,))
        return bool(deleted)

    def list_videos(self, channel_row_id: str, limit: int = 8) -> list[dict]:
        sql = "SELECT * FROM youtube_videos WHERE channel_row_id=%s ORDER BY published_at DESC LIMIT %s"
        with connect_mysql(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (channel_row_id, limit))
                return [self._video_row(row) for row in cursor.fetchall()]

    def get_video(self, video_id: str) -> dict | None:
        return self._one("SELECT * FROM youtube_videos WHERE video_id=%s LIMIT 1", (video_id,), self._video_row)

    def save_video(self, data: dict) -> dict:
        existing = self.get_video(data["video_id"])
        segments = data.get("transcript_segments", [])
        payload = {
            key: value for key, value in data.items() if key != "transcript_segments"
        }
        payload.update(
            {
            "audio_duration_ms": int(data.get("audio_duration_ms", 0)),
            "transcript_segments_json": json.dumps(segments, ensure_ascii=False),
            "created_at": existing["created_at"] if existing else data["updated_at"],
            }
        )
        sql = """
            INSERT INTO youtube_videos (
                video_id, channel_row_id, channel_id, title, video_url, published_at,
                audio_path, audio_duration_ms, transcript_status, transcript_language, transcript_source,
                transcript_text, transcript_segments_json, error_message, synced_at, created_at, updated_at
            ) VALUES (
                %(video_id)s, %(channel_row_id)s, %(channel_id)s, %(title)s, %(video_url)s, %(published_at)s,
                %(audio_path)s, %(audio_duration_ms)s, %(transcript_status)s, %(transcript_language)s, %(transcript_source)s,
                %(transcript_text)s, %(transcript_segments_json)s, %(error_message)s, %(synced_at)s, %(created_at)s, %(updated_at)s
            )
            ON DUPLICATE KEY UPDATE
                title=VALUES(title),
                video_url=VALUES(video_url),
                published_at=VALUES(published_at),
                audio_path=VALUES(audio_path),
                audio_duration_ms=VALUES(audio_duration_ms),
                transcript_status=VALUES(transcript_status),
                transcript_language=VALUES(transcript_language),
                transcript_source=VALUES(transcript_source),
                transcript_text=VALUES(transcript_text),
                transcript_segments_json=VALUES(transcript_segments_json),
                error_message=VALUES(error_message),
                synced_at=VALUES(synced_at),
                updated_at=VALUES(updated_at)
        """
        self._execute(sql, payload)
        return self.get_video(data["video_id"])

    def _database_sql(self) -> str:
        database = self._config.database.replace("`", "``")
        collation = "utf8mb4_unicode_ci" if self._config.charset == "utf8mb4" else "utf8_general_ci"
        return f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET {self._config.charset} COLLATE {collation}"

    def _execute(self, sql: str, params: dict) -> None:
        with connect_mysql(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)

    def _one(self, sql: str, params: tuple, mapper):
        with connect_mysql(self._config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
        return mapper(row) if row else None

    @staticmethod
    def _channel_row(row: dict) -> dict:
        data = dict(row)
        data["enabled"] = bool(data["enabled"])
        return data

    @staticmethod
    def _video_row(row: dict) -> dict:
        data = dict(row)
        data["transcript_segments"] = json.loads(data["transcript_segments_json"] or "[]")
        data.pop("transcript_segments_json", None)
        return data
