"""Bitget classic demo futures adapter."""

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx
import pymysql
from pymysql.cursors import DictCursor

from app.config import AppConfig
from app.trading.models import TradeIntent


class BitgetDemoExchange:
    def __init__(self, config: AppConfig):
        self._config = config

    def place_order(self, intent: TradeIntent, client_oid: str) -> dict:
        credential = self._credential()
        body = {
            "symbol": intent.symbol,
            "productType": self._config.trading.product_type,
            "marginMode": self._config.trading.margin_mode,
            "marginCoin": self._config.trading.margin_coin,
            "size": _num(intent.quantity),
            "price": _num(intent.entry_price),
            "side": "buy" if intent.side == "long" else "sell",
            "tradeSide": "open",
            "orderType": intent.order_type,
            "force": "gtc",
            "clientOid": client_oid,
        }
        response = self._request("POST", "/api/v2/mix/order/place-order", body, credential)
        data = response.get("data") or {}
        ok = response.get("code") == "00000"
        return {
            "exchange": "bitget",
            "status": "submitted" if ok else "failed",
            "client_oid": client_oid,
            "order_id": str(data.get("orderId") or ""),
            "error": "" if ok else str(response.get("msg") or response.get("code") or ""),
            "raw": response,
        }

    def close_position(self, symbol: str, hold_side: str, size, client_oid: str) -> dict:
        side = "buy" if hold_side == "long" else "sell"
        body = {
            "symbol": symbol,
            "productType": self._config.trading.product_type,
            "marginMode": self._config.trading.margin_mode,
            "marginCoin": self._config.trading.margin_coin,
            "size": _num(size),
            "side": side,
            "tradeSide": "close",
            "orderType": "market",
            "clientOid": client_oid,
        }
        response = self._request("POST", "/api/v2/mix/order/place-order", body)
        data = response.get("data") or {}
        ok = response.get("code") == "00000"
        return {
            "exchange": "bitget",
            "status": "submitted" if ok else "failed",
            "client_oid": client_oid,
            "order_id": str(data.get("orderId") or ""),
            "error": "" if ok else str(response.get("msg") or response.get("code") or ""),
            "raw": response,
        }

    def get_accounts(self) -> dict:
        return self._request(
            "GET",
            "/api/v2/mix/account/accounts",
            query={"productType": self._config.trading.product_type},
        )

    def get_positions(self) -> dict:
        return self._request(
            "GET",
            "/api/v2/mix/position/all-position",
            query={
                "productType": self._config.trading.product_type,
                "marginCoin": self._config.trading.margin_coin,
            },
        )

    def get_pending_orders(self) -> dict:
        return self._request(
            "GET",
            "/api/v2/mix/order/orders-pending",
            query={"productType": self._config.trading.product_type},
        )

    def get_history_positions(self, limit: int = 50) -> dict:
        return self._request(
            "GET",
            "/api/v2/mix/position/history-position",
            query={
                "productType": self._config.trading.product_type,
                "limit": max(1, min(limit, 100)),
            },
        )

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        credential: dict | None = None,
        query: dict | None = None,
    ) -> dict:
        credential = credential or self._credential()
        body_text = json.dumps(body or {}, separators=(",", ":")) if body else ""
        timestamp = str(int(time.time() * 1000))
        request_path = path + _query(query)
        signature = _signature(
            credential["api_secret"], timestamp, method, request_path, body_text,
        )
        last_error = None
        for _ in range(2):
            result = self._try_request(method, request_path, body_text, credential, signature, timestamp)
            if result.get("code") != "NETWORK_ERROR":
                return result
            last_error = result
        return last_error or {"code": "NETWORK_ERROR", "msg": "request failed"}

    def _try_request(
        self,
        method: str,
        request_path: str,
        body_text: str,
        credential: dict,
        signature: str,
        timestamp: str,
    ) -> dict:
        try:
            with httpx.Client(proxy=self._proxy(), timeout=20) as client:
                response = client.request(
                    method,
                    f"https://api.bitget.com{request_path}",
                    content=body_text or None,
                    headers={
                        "ACCESS-KEY": credential["api_key"],
                        "ACCESS-SIGN": signature,
                        "ACCESS-TIMESTAMP": timestamp,
                        "ACCESS-PASSPHRASE": credential["passphrase"],
                        "Content-Type": "application/json",
                        "locale": "en-US",
                        "paptrading": "1",
                    },
                )
            return response.json()
        except json.JSONDecodeError:
            return {"code": "HTTP_ERROR", "msg": response.text}
        except httpx.HTTPError as exc:
            return {"code": "NETWORK_ERROR", "msg": str(exc)}

    def _proxy(self) -> str | None:
        proxy = self._config.trading.proxy_url.strip()
        return proxy or None

    def _credential(self) -> dict:
        sql = """
            SELECT api_key, api_secret, passphrase
            FROM exchange_credentials
            WHERE provider='bitget' AND account_type='classic'
              AND environment='demo' AND enabled=TRUE
            LIMIT 1
        """
        mysql = self._config.mysql
        with pymysql.connect(
            host=mysql.host, port=mysql.port, user=mysql.user,
            password=mysql.password, database=self._config.trading.credential_database,
            charset=mysql.charset, autocommit=True, cursorclass=DictCursor,
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                row = cursor.fetchone()
        if not row:
            raise RuntimeError("Bitget demo credentials not found")
        return row


def _signature(secret: str, timestamp: str, method: str, path: str, body: str) -> str:
    payload = f"{timestamp}{method}{path}{body}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _num(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _query(values: dict | None) -> str:
    return f"?{urlencode(values)}" if values else ""
