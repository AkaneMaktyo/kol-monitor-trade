"""Account overview persistence."""

import json

import pymysql
from pymysql.cursors import DictCursor

from app.config import MySQLConfig
from app.models import utc_now


class AccountStore:
    def __init__(self, config: MySQLConfig):
        self._config = config

    def initialize(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(self._snapshot_table())

    def save_snapshot(self, account: dict) -> str:
        snapshot_id = f"acct_{utc_now().replace(' ', '_').replace(':', '')}"
        data = _numbers(account, "accountEquity", "available", "unrealizedPL", "locked")
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO account_snapshots(
                      id, exchange_name, account_type, margin_coin, account_equity,
                      available, unrealized_pl, locked, response_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE response_json=VALUES(response_json)
                    """, (
                        snapshot_id, "bitget", "demo", account.get("marginCoin", "USDT"),
                        data["accountEquity"], data["available"], data["unrealizedPL"],
                        data["locked"], json.dumps(account, ensure_ascii=False), utc_now(),
                    ))
        return snapshot_id

    def list_snapshots(self, limit: int = 120) -> list[dict]:
        sql = """
            SELECT created_at, margin_coin, account_equity, available, unrealized_pl, locked
            FROM account_snapshots
            ORDER BY created_at DESC
            LIMIT %s
        """
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (max(1, min(limit, 300)),))
                rows = cursor.fetchall()
        return list(reversed([_row(row) for row in rows]))

    def list_trade_orders(self, limit: int = 30) -> list[dict]:
        sql = """
            SELECT ti.source_log_id, ti.symbol, ti.side, ti.order_type, ti.price,
                   ti.quantity, ti.status AS intent_status, ti.created_at,
                   eo.status AS order_status, eo.exchange_order_id, eo.client_order_id
            FROM trade_intents ti
            LEFT JOIN exchange_orders eo ON eo.intent_id = ti.id
            ORDER BY ti.updated_at DESC
            LIMIT %s
        """
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (max(1, min(limit, 100)),))
                return [_row(row) for row in cursor.fetchall()]

    def list_signal_updates(self, limit: int = 20) -> list[dict]:
        sql = """
            SELECT su.source_log_id, su.related_signal_id,
                   ts.source_log_id AS related_source_log_id,
                   su.action, su.close_fraction, su.status,
                   su.reasons_json, su.updated_at
            FROM signal_updates su
            LEFT JOIN signal_candidates ts ON ts.id = su.related_signal_id
            ORDER BY su.updated_at DESC
            LIMIT %s
        """
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (max(1, min(limit, 100)),))
                return [_row(row) for row in cursor.fetchall()]

    def _connect(self):
        return pymysql.connect(
            host=self._config.host, port=self._config.port,
            user=self._config.user, password=self._config.password,
            database=self._config.database, charset=self._config.charset,
            autocommit=True, cursorclass=DictCursor,
        )

    @staticmethod
    def _snapshot_table() -> str:
        return """
            CREATE TABLE IF NOT EXISTS account_snapshots (
              id VARCHAR(80) PRIMARY KEY, exchange_name VARCHAR(32) NOT NULL,
              account_type VARCHAR(32) NOT NULL, margin_coin VARCHAR(16) NOT NULL,
              account_equity DECIMAL(20, 8), available DECIMAL(20, 8),
              unrealized_pl DECIMAL(20, 8), locked DECIMAL(20, 8),
              response_json MEDIUMTEXT, created_at VARCHAR(32) NOT NULL,
              INDEX idx_account_snapshot_time(created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """


def _numbers(row: dict, *keys: str) -> dict:
    return {key: float(row.get(key) or 0) for key in keys}


def _row(row: dict) -> dict:
    return {key: float(value) if hasattr(value, "as_tuple") else value for key, value in row.items()}
