"""Bitget classic demo futures adapter."""

import base64
import hashlib
import hmac
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
        return {
            "exchange": "bitget",
            "status": "submitted" if response.get("code") == "00000" else "failed",
            "client_oid": client_oid,
            "order_id": str(data.get("orderId") or ""),
            "raw": response,
        }

    def _request(self, method: str, path: str, body: dict, credential: dict) -> dict:
        body_text = json.dumps(body, separators=(",", ":"))
        timestamp = str(int(time.time() * 1000))
        signature = _signature(credential["api_secret"], timestamp, method, path, body_text)
        request = Request(
            f"https://api.bitget.com{path}",
            data=body_text.encode("utf-8"),
            method=method,
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
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"code": "HTTP_ERROR", "msg": text}
        except URLError as exc:
            return {"code": "NETWORK_ERROR", "msg": str(exc.reason)}

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
