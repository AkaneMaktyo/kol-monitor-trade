"""大模型供应商配置存储。"""

import pymysql
from pymysql.cursors import DictCursor

from app.config import MySQLConfig
from app.models import utc_now


DEFAULT_PROVIDER = "deepseek"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


class LlmConfigStore:
    def __init__(self, config: MySQLConfig):
        self._config = config

    def initialize(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(self._create_table_sql())

    def get(self, provider: str = DEFAULT_PROVIDER, include_key: bool = False) -> dict:
        sql = "SELECT * FROM llm_provider_configs WHERE provider=%s LIMIT 1"
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (provider,))
                row = cursor.fetchone()
        if row:
            return self._row_dict(row, include_key=include_key)
        return {
            "provider": provider,
            "base_url": DEFAULT_BASE_URL,
            "model": DEFAULT_MODEL,
            "api_key": "" if include_key else None,
            "has_api_key": False,
            "enabled": False,
            "updated_at": "",
        }

    def save(self, data: dict) -> dict:
        current = self.get(data.get("provider") or DEFAULT_PROVIDER, include_key=True)
        provider = data.get("provider") or DEFAULT_PROVIDER
        api_key = data.get("api_key", "")
        if not api_key and current["has_api_key"]:
            api_key = current["api_key"]
        payload = {
            "provider": provider,
            "base_url": (data.get("base_url") or DEFAULT_BASE_URL).strip().rstrip("/"),
            "model": (data.get("model") or DEFAULT_MODEL).strip(),
            "api_key": api_key.strip(),
            "enabled": 1 if data.get("enabled", True) else 0,
            "updated_at": utc_now(),
        }
        sql = """
            INSERT INTO llm_provider_configs (
                provider, base_url, model, api_key, enabled, updated_at
            ) VALUES (
                %(provider)s, %(base_url)s, %(model)s, %(api_key)s,
                %(enabled)s, %(updated_at)s
            )
            ON DUPLICATE KEY UPDATE
                base_url=VALUES(base_url),
                model=VALUES(model),
                api_key=VALUES(api_key),
                enabled=VALUES(enabled),
                updated_at=VALUES(updated_at)
        """
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, payload)
        return self.get(provider)

    def _connect(self):
        return pymysql.connect(
            host=self._config.host,
            port=self._config.port,
            user=self._config.user,
            password=self._config.password,
            database=self._config.database,
            charset=self._config.charset,
            autocommit=True,
            cursorclass=DictCursor,
        )

    @staticmethod
    def _create_table_sql() -> str:
        return """
            CREATE TABLE IF NOT EXISTS llm_provider_configs (
                provider VARCHAR(40) PRIMARY KEY,
                base_url VARCHAR(255) NOT NULL,
                model VARCHAR(120) NOT NULL,
                api_key TEXT NOT NULL,
                enabled TINYINT(1) NOT NULL DEFAULT 0,
                updated_at VARCHAR(32) NOT NULL,
                INDEX idx_llm_enabled (enabled)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """

    @staticmethod
    def _row_dict(row: dict, include_key: bool = False) -> dict:
        data = dict(row)
        api_key = data.pop("api_key") or ""
        data["enabled"] = bool(data["enabled"])
        data["has_api_key"] = bool(api_key)
        if include_key:
            data["api_key"] = api_key
        return data
