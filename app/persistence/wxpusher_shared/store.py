import hashlib, json
from dataclasses import dataclass
from datetime import datetime, timezone
from app.config import MySQLConfig, WxPusherConfig
from app.models import app_now
from app.persistence import connect_mysql
from app.persistence.wxpusher_shared.schema import CONSUMER_STATE_SQL, RAW_MESSAGES_SQL, SETTINGS_SQL
@dataclass(frozen=True)
class SharedWxPusherSettings:
    device_token: str
    push_token: str
    device_uuid: str
    platform: str
    version: str
    poll_interval_seconds: int
    enable_polling: bool
    enable_websocket: bool
    @classmethod
    def from_config(cls, config: WxPusherConfig) -> "SharedWxPusherSettings":
        return cls(
            config.device_token,
            config.push_token,
            config.device_uuid,
            config.platform,
            config.version,
            config.poll_interval_seconds,
            config.enable_polling,
            config.enable_websocket,
        )
    def apply(self, config: WxPusherConfig) -> None:
        config.device_token = self.device_token
        config.push_token = self.push_token
        config.device_uuid = self.device_uuid
        config.platform = self.platform
        config.version = self.version
        config.poll_interval_seconds = self.poll_interval_seconds
        config.enable_polling = self.enable_polling
        config.enable_websocket = self.enable_websocket
class SharedWxPusherStore:
    def __init__(self, config: MySQLConfig, database: str):
        self._config = config
        self._database = database.strip() or "market_opinion_tracker"
    def initialize(self) -> None:
        self._create_database()
        with connect_mysql(self._config, database=self._database) as conn:
            with conn.cursor() as cursor:
                cursor.execute(SETTINGS_SQL)
                self._ensure_last_poll_at(cursor)
                cursor.execute(RAW_MESSAGES_SQL)
                cursor.execute(CONSUMER_STATE_SQL)
    def ensure_settings(self, defaults: SharedWxPusherSettings) -> None:
        now = app_now()
        values = (
            "default",
            defaults.device_token,
            defaults.push_token,
            defaults.device_uuid,
            defaults.platform,
            defaults.version,
            defaults.poll_interval_seconds,
            int(defaults.enable_polling),
            int(defaults.enable_websocket),
            now,
            now,
        )
        fill_defaults = (
            defaults.device_token,
            defaults.push_token,
            defaults.device_uuid,
            defaults.platform,
            defaults.version,
            now,
        )
        with connect_mysql(self._config, database=self._database) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT IGNORE INTO wxpusher_settings(
                      id, device_token, push_token, device_uuid, platform, version,
                      poll_interval_seconds, enable_polling, enable_websocket,
                      last_heartbeat_at, last_error, last_poll_at, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, '', '', '', %s, %s)
                    """,
                    values,
                )
                cursor.execute(
                    """
                    UPDATE wxpusher_settings
                    SET device_token = CASE WHEN device_token = '' THEN %s ELSE device_token END,
                        push_token = CASE WHEN push_token = '' THEN %s ELSE push_token END,
                        device_uuid = CASE WHEN device_uuid = '' THEN %s ELSE device_uuid END,
                        platform = CASE WHEN platform = '' THEN %s ELSE platform END,
                        version = CASE WHEN version = '' THEN %s ELSE version END,
                        updated_at = %s
                    WHERE id = 'default'
                    """,
                    fill_defaults,
                )
    def load_settings(self, defaults: SharedWxPusherSettings) -> SharedWxPusherSettings:
        with connect_mysql(self._config, database=self._database) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM wxpusher_settings WHERE id='default' LIMIT 1")
                row = cursor.fetchone() or {}
        return SharedWxPusherSettings(
            self._value(row, "device_token", defaults.device_token),
            self._value(row, "push_token", defaults.push_token),
            self._value(row, "device_uuid", defaults.device_uuid),
            self._value(row, "platform", defaults.platform),
            self._value(row, "version", defaults.version),
            max(30, int(row.get("poll_interval_seconds") or defaults.poll_interval_seconds)),
            bool(row.get("enable_polling", defaults.enable_polling)),
            bool(row.get("enable_websocket", defaults.enable_websocket)),
        )
    def update_runtime(self, *, heartbeat_at: str | None = None, error: str | None = None, poll_at: str | None = None) -> None:
        with connect_mysql(self._config, database=self._database) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE wxpusher_settings
                    SET last_heartbeat_at = COALESCE(%s, last_heartbeat_at),
                        last_error = COALESCE(%s, last_error),
                        last_poll_at = COALESCE(%s, last_poll_at),
                        updated_at = %s
                    WHERE id = 'default'
                    """,
                    (self._clean(heartbeat_at), self._clean(error), self._clean(poll_at), app_now()),
                )
    def save_message(self, channel: str, item: dict) -> None:
        key = self._message_key(item, channel)
        now = app_now()
        payload = (
            self._raw_message_id(key),
            key,
            channel,
            self._source_name(item),
            str(item.get("title") or "")[:500],
            str(item.get("summary") or ""),
            str(item.get("url") or "")[:1000],
            str(item.get("sourceUrl") or "")[:1000],
            self._message_time(item),
            json.dumps(item, ensure_ascii=False),
            now,
            now,
        )
        with connect_mysql(self._config, database=self._database) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO wxpusher_raw_messages(
                      id, message_key, channel, source_name, title, summary, detail_url, source_url,
                      message_time, raw_payload_json, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      source_name = VALUES(source_name), title = VALUES(title), summary = VALUES(summary),
                      detail_url = VALUES(detail_url), source_url = VALUES(source_url),
                      message_time = VALUES(message_time), raw_payload_json = VALUES(raw_payload_json),
                      updated_at = VALUES(updated_at)
                    """,
                    payload,
                )
    def _create_database(self) -> None:
        quoted = f"`{self._database.replace('`', '``')}`"
        with connect_mysql(self._config, use_database=False) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS {quoted} "
                    f"CHARACTER SET {self._config.charset} COLLATE utf8mb4_unicode_ci"
                )

    @staticmethod
    def _ensure_last_poll_at(cursor) -> None:
        cursor.execute("SHOW COLUMNS FROM wxpusher_settings LIKE 'last_poll_at'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE wxpusher_settings ADD COLUMN last_poll_at VARCHAR(64)")
    @staticmethod
    def _value(row: dict, key: str, default: str) -> str:
        return (row.get(key) or default).strip()
    @staticmethod
    def _clean(value: str | None) -> str | None:
        return None if value is None else value.strip()
    @staticmethod
    def _source_name(item: dict) -> str:
        return str(item.get("name") or "").strip()[:255] or "WxPusher"
    @staticmethod
    def _message_key(item: dict, channel: str) -> str:
        raw = str(item.get("sourceUrl") or item.get("url") or "").strip()
        if raw:
            return f"wxpusher:{raw}"
        fallback = item.get("qid") if channel == "websocket" else item.get("messageId") or item.get("id")
        return f"{channel}:{fallback or item.get('createTime') or ''}:{item.get('summary') or ''}"
    @staticmethod
    def _message_time(item: dict) -> str:
        try:
            value = int(item.get("createTime"))
        except (TypeError, ValueError):
            return app_now()
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    @staticmethod
    def _raw_message_id(message_key: str) -> str:
        return hashlib.sha1(message_key.encode("utf-8")).hexdigest()
