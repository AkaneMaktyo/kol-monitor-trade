"""Read models for the dashboard signal board."""

from app.config import MySQLConfig
from app.persistence import connect_mysql


class SignalBoardStore:
    def __init__(self, config: MySQLConfig):
        self._config = config

    def snapshot(self, limit: int = 6) -> dict:
        return {
            "ready": self._ready(limit),
            "review": self._review(limit),
            "updates": self._updates(limit),
            "orders": self._orders(limit),
        }

    def _ready(self, limit: int) -> list[dict]:
        sql = """
            SELECT sc.source_log_id, sc.symbol, sc.side, sc.raw_text, sc.created_at,
                   sc.parsed_json, ti.order_type, ti.price, ti.quantity, ti.status AS intent_status,
                   ti.reasons_json, ti.request_json, ti.updated_at, eo.status AS order_status,
                   eo.exchange_order_id, eo.error_message
            FROM signal_candidates sc
            JOIN trade_intents ti ON ti.signal_id = sc.id
            LEFT JOIN exchange_orders eo ON eo.intent_id = ti.id
            WHERE sc.category='new_signal' AND ti.status='ready'
            ORDER BY ti.updated_at DESC
            LIMIT %s
        """
        return self._fetch(sql, limit)

    def _review(self, limit: int) -> list[dict]:
        sql = """
            SELECT sc.source_log_id, sc.symbol, sc.side, sc.raw_text, sc.created_at,
                   sc.status AS candidate_status, sc.parsed_json, ti.order_type, ti.price,
                   ti.quantity, ti.status AS intent_status, ti.reasons_json, ti.request_json,
                   ti.updated_at, eo.status AS order_status, eo.error_message
            FROM signal_candidates sc
            LEFT JOIN trade_intents ti ON ti.signal_id = sc.id
            LEFT JOIN exchange_orders eo ON eo.intent_id = ti.id
            WHERE sc.category='new_signal' AND (ti.id IS NULL OR ti.status <> 'ready')
            ORDER BY COALESCE(ti.updated_at, sc.created_at) DESC
            LIMIT %s
        """
        return self._fetch(sql, limit)

    def _updates(self, limit: int) -> list[dict]:
        sql = """
            SELECT su.source_log_id, su.related_signal_id, su.action, su.close_fraction,
                   su.status, su.reasons_json, su.request_json, su.updated_at,
                   sc.symbol, sc.side
            FROM signal_updates su
            LEFT JOIN signal_candidates sc ON sc.id = su.related_signal_id
            ORDER BY su.updated_at DESC
            LIMIT %s
        """
        return self._fetch(sql, limit)

    def _orders(self, limit: int) -> list[dict]:
        sql = """
            SELECT ti.source_log_id, ti.symbol, ti.side, ti.order_type, ti.price,
                   ti.quantity, ti.status AS intent_status, ti.request_json,
                   eo.status AS order_status, eo.exchange_order_id,
                   eo.error_message, eo.updated_at
            FROM exchange_orders eo
            JOIN trade_intents ti ON ti.id = eo.intent_id
            ORDER BY eo.updated_at DESC
            LIMIT %s
        """
        return self._fetch(sql, limit)

    def _fetch(self, sql: str, limit: int) -> list[dict]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (max(1, min(limit, 20)),))
                return [_row(row) for row in cursor.fetchall()]

    def _connect(self):
        return connect_mysql(self._config)


def _row(row: dict) -> dict:
    return {
        key: float(value) if hasattr(value, "as_tuple") else value
        for key, value in row.items()
    }
