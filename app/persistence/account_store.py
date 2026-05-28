"""Account overview persistence."""

import itertools
import json
from datetime import datetime, timedelta

from app.config import MySQLConfig
from app.models import app_now
from app.persistence import connect_mysql


class AccountStore:
    def __init__(self, config: MySQLConfig):
        self._config = config

    def initialize(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(self._snapshot_table())

    def save_snapshot(self, account: dict) -> str:
        snapshot_id = f"acct_{app_now().replace(' ', '_').replace(':', '')}"
        data = _numbers(account, "accountEquity", "available", "unrealizedPL", "locked")
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO account_snapshots(
                      id, exchange_name, account_type, margin_coin, account_equity,
                      available, unrealized_pl, locked, response_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE response_json=VALUES(response_json)
                    """,
                    (
                        snapshot_id, "bitget", "demo", account.get("marginCoin", "USDT"),
                        data["accountEquity"], data["available"], data["unrealizedPL"],
                        data["locked"], json.dumps(account, ensure_ascii=False), app_now(),
                    ),
                )
        return snapshot_id

    def list_snapshots(self, limit: int = 120) -> list[dict]:
        sql = """
            SELECT created_at, margin_coin, account_equity, available, unrealized_pl, locked
            FROM account_snapshots
            ORDER BY created_at DESC
            LIMIT %s
        """
        return list(reversed(self._fetch(sql, max(1, min(limit, 300)))))

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
        return self._fetch(sql, max(1, min(limit, 100)))

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
        return self._fetch(sql, max(1, min(limit, 100)))

    def get_history_lifecycle(
        self,
        *,
        symbol: str,
        hold_side: str,
        closed_at_ms: int,
        open_price: float,
        open_size: float,
    ) -> dict:
        pool = self._history_signal_pool(symbol, hold_side, _text_time(closed_at_ms))
        matched = _pick_candidates(pool, open_price, open_size)
        updates = self._history_updates([row["signal_id"] for row in matched], closed_at_ms)
        return {
            "signals": matched,
            "updates": updates,
            "pool_size": len(pool),
            "matched_size": len(matched),
        }

    def _history_signal_pool(self, symbol: str, hold_side: str, closed_at: str) -> list[dict]:
        sql = """
            SELECT sc.id AS signal_id, sc.source_log_id, sc.status AS signal_status,
                   sc.raw_text, sc.parsed_json, sc.created_at AS signal_time,
                   ti.order_type, ti.price, ti.quantity, ti.status AS intent_status,
                   eo.status AS order_status, eo.exchange_order_id, eo.error_message,
                   eo.updated_at AS order_time, le.timestamp AS message_time,
                   le.platform, le.author, le.source_channel, le.content
            FROM signal_candidates sc
            JOIN trade_intents ti ON ti.signal_id = sc.id
            LEFT JOIN exchange_orders eo ON eo.intent_id = ti.id
            LEFT JOIN log_entries le ON le.id = sc.source_log_id
            WHERE sc.category='new_signal' AND sc.symbol=%s AND sc.side=%s
              AND ti.created_at BETWEEN %s AND %s
              AND ti.quantity > 0
            ORDER BY ti.created_at ASC
        """
        start_at = _window_start(closed_at, days=10)
        return self._fetch(sql, symbol, hold_side, start_at, closed_at)

    def _history_updates(self, signal_ids: list[str], closed_at_ms: int) -> list[dict]:
        if not signal_ids:
            return []
        marks = ",".join(["%s"] * len(signal_ids))
        sql = f"""
            SELECT su.source_log_id, su.related_signal_id, su.action, su.close_fraction,
                   su.status, su.updated_at, le.timestamp AS message_time,
                   le.platform, le.author, le.source_channel, le.content
            FROM signal_updates su
            LEFT JOIN log_entries le ON le.id = su.source_log_id
            WHERE su.related_signal_id IN ({marks})
              AND su.updated_at <= %s
            ORDER BY su.updated_at ASC
        """
        return self._fetch(sql, *signal_ids, _text_time(closed_at_ms))

    def _fetch(self, sql: str, *params) -> list[dict]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return [_row(row) for row in cursor.fetchall()]

    def _connect(self):
        return connect_mysql(self._config)

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


def _pick_candidates(rows: list[dict], target_price: float, target_size: float) -> list[dict]:
    if not rows:
        return []
    target_size = max(float(target_size or 0), 0.0)
    target_price = max(float(target_price or 0), 0.0)
    best = rows[:1]
    best_score = _score(rows[:1], target_price, target_size)
    for size in range(1, len(rows) + 1):
        for combo in itertools.combinations(rows, size):
            score = _score(list(combo), target_price, target_size)
            if score < best_score:
                best = list(combo)
                best_score = score
    return best


def _score(rows: list[dict], target_price: float, target_size: float) -> float:
    total = sum(float(row.get("quantity") or 0) for row in rows) or 1.0
    average = sum(float(row.get("price") or 0) * float(row.get("quantity") or 0) for row in rows) / total
    dry_run_penalty = sum(1 for row in rows if row.get("order_status") == "dry_run") * 8
    blocked_penalty = sum(1 for row in rows if row.get("order_status") == "blocked") * 15
    return abs(total - target_size) * 200 + abs(average - target_price) + dry_run_penalty + blocked_penalty


def _window_start(closed_at: str, *, days: int) -> str:
    return (datetime.strptime(closed_at, "%Y-%m-%d %H:%M:%S") - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _text_time(value: int) -> str:
    return datetime.fromtimestamp(max(int(value or 0), 1) / 1000).strftime("%Y-%m-%d %H:%M:%S")


def _numbers(row: dict, *keys: str) -> dict:
    return {key: float(row.get(key) or 0) for key in keys}


def _row(row: dict) -> dict:
    data = {
        key: float(value) if hasattr(value, "as_tuple") else value
        for key, value in row.items()
    }
    if data.get("parsed_json"):
        data["parsed_json"] = _json_object(data["parsed_json"])
    return data


def _json_object(value) -> dict:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
