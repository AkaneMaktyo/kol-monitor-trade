"""Trading audit storage."""

import json
import pymysql
from pymysql.cursors import DictCursor

from app.config import MySQLConfig
from app.models import utc_now
from app.signals.models import SignalCandidate
from app.trading.models import TradeIntent


class TradingStore:
    def __init__(self, config: MySQLConfig):
        self._config = config

    def initialize(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(self._signal_table())
                cursor.execute(self._intent_table())
                cursor.execute(self._order_table())

    def save_candidate(self, candidate: SignalCandidate) -> str:
        signal_id = f"signal_{candidate.source_log_id}"[:80]
        payload = candidate.to_dict()
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO signal_candidates(
                      id, source_log_id, category, symbol, side, confidence,
                      missing_fields_json, raw_text, parsed_json, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      category=VALUES(category), parsed_json=VALUES(parsed_json),
                      status=VALUES(status)
                    """, (
                        signal_id, candidate.source_log_id, candidate.category,
                        candidate.bitget_symbol or candidate.symbol, candidate.side,
                        candidate.confidence, json.dumps(candidate.missing_fields),
                        candidate.raw_text, json.dumps(payload, ensure_ascii=False),
                        candidate.status, utc_now(),
                    ))
        return signal_id

    def save_intent(self, signal_id: str, intent: TradeIntent) -> str:
        intent_id = f"intent_{intent.source_log_id}"[:80]
        data = intent.to_dict()
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO trade_intents(
                      id, signal_id, source_log_id, exchange_name, symbol, side,
                      order_type, price, quantity, dry_run, status, reasons_json,
                      request_json, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      status=VALUES(status), reasons_json=VALUES(reasons_json),
                      request_json=VALUES(request_json), updated_at=VALUES(updated_at)
                    """, (
                        intent_id, signal_id, intent.source_log_id, intent.exchange,
                        intent.symbol, intent.side, intent.order_type,
                        intent.entry_price, intent.quantity, int(intent.dry_run),
                        intent.status, json.dumps(intent.reasons),
                        json.dumps(data, ensure_ascii=False), utc_now(), utc_now(),
                    ))
        return intent_id

    def save_order(self, intent_id: str, response: dict) -> str:
        order_id = f"order_{intent_id.replace('intent_', '')}"[:80]
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO exchange_orders(
                      id, intent_id, exchange_name, client_order_id,
                      exchange_order_id, status, response_json,
                      error_message, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      exchange_order_id=VALUES(exchange_order_id), status=VALUES(status),
                      response_json=VALUES(response_json), error_message=VALUES(error_message),
                      updated_at=VALUES(updated_at)
                    """, (
                        order_id, intent_id, response.get("exchange", "bitget"),
                        response.get("client_oid", ""), response.get("order_id", ""),
                        response.get("status", ""), json.dumps(response, ensure_ascii=False),
                        response.get("error", ""), utc_now(), utc_now(),
                    ))
        return order_id

    def _connect(self):
        return pymysql.connect(
            host=self._config.host, port=self._config.port,
            user=self._config.user, password=self._config.password,
            database=self._config.database, charset=self._config.charset,
            autocommit=True, cursorclass=DictCursor,
        )

    @staticmethod
    def _signal_table() -> str:
        return """
            CREATE TABLE IF NOT EXISTS signal_candidates (
              id VARCHAR(80) PRIMARY KEY, source_log_id VARCHAR(80) NOT NULL UNIQUE,
              category VARCHAR(32) NOT NULL, symbol VARCHAR(64), side VARCHAR(16),
              confidence DECIMAL(5, 2), missing_fields_json TEXT, raw_text MEDIUMTEXT,
              parsed_json MEDIUMTEXT, status VARCHAR(32), created_at VARCHAR(32) NOT NULL,
              INDEX idx_signal_status(status), INDEX idx_signal_category(category)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """

    @staticmethod
    def _intent_table() -> str:
        return """
            CREATE TABLE IF NOT EXISTS trade_intents (
              id VARCHAR(80) PRIMARY KEY, signal_id VARCHAR(80) NOT NULL,
              source_log_id VARCHAR(80) NOT NULL, exchange_name VARCHAR(32) NOT NULL,
              symbol VARCHAR(64) NOT NULL, side VARCHAR(16) NOT NULL,
              order_type VARCHAR(16) NOT NULL, price DECIMAL(20, 8),
              quantity DECIMAL(20, 8), dry_run TINYINT(1) NOT NULL,
              status VARCHAR(32) NOT NULL, reasons_json TEXT, request_json MEDIUMTEXT,
              created_at VARCHAR(32) NOT NULL, updated_at VARCHAR(32) NOT NULL,
              INDEX idx_intent_signal(signal_id), INDEX idx_intent_status(status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """

    @staticmethod
    def _order_table() -> str:
        return """
            CREATE TABLE IF NOT EXISTS exchange_orders (
              id VARCHAR(80) PRIMARY KEY, intent_id VARCHAR(80) NOT NULL,
              exchange_name VARCHAR(32) NOT NULL, client_order_id VARCHAR(120),
              exchange_order_id VARCHAR(120), status VARCHAR(32) NOT NULL,
              response_json MEDIUMTEXT, error_message TEXT,
              created_at VARCHAR(32) NOT NULL, updated_at VARCHAR(32) NOT NULL,
              INDEX idx_order_intent(intent_id), INDEX idx_order_status(status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
