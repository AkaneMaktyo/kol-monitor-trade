import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import AppConfig
from app.exchanges.bitget import BitgetDemoExchange
from app.routes import account


class BitgetClosePositionTests(unittest.TestCase):
    def test_market_close_position_uses_market_body(self):
        body = self._close(order_type="market", price=None)
        self.assertEqual(body["orderType"], "market")
        self.assertNotIn("price", body)

    def test_limit_close_position_sends_price_and_force(self):
        body = self._close(order_type="limit", price=Decimal("123.45"))
        self.assertEqual(body["orderType"], "limit")
        self.assertEqual(body["price"], "123.45")
        self.assertEqual(body["force"], "gtc")

    def _close(self, order_type: str, price):
        exchange = BitgetDemoExchange(AppConfig())
        with patch.object(exchange, "_request", return_value={"code": "00000", "data": {}}) as request:
            exchange.close_position("BTCUSDT", "long", Decimal("1.25"), "oid_1", order_type=order_type, price=price)
        return request.call_args.args[2]


class ClosePositionRouteTests(unittest.TestCase):
    def test_internal_error_returns_json_detail(self):
        app = FastAPI()
        app.state.config = AppConfig()
        app.include_router(account.router)
        with patch("app.routes.account.AccountActionService.close_position", side_effect=RuntimeError("boom")):
            response = TestClient(app).post("/api/account/close-position", json=_payload())
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "boom")


class BitgetPlaceTpslTests(unittest.TestCase):
    def test_place_position_tpsl_includes_trigger_prices(self):
        body = self._tpsl(stop_loss=Decimal("4508.11"), take_profits=[Decimal("4548.11"), Decimal("4560")])
        self.assertEqual(body["stopSurplusTriggerPrice"], "4548.11")
        self.assertEqual(body["stopLossTriggerPrice"], "4508.11")
        self.assertEqual(body["holdSide"], "short")

    def test_place_position_tpsl_skips_empty_values(self):
        body = self._tpsl(stop_loss=Decimal("0"), take_profits=[])
        self.assertEqual(body, {})

    def _tpsl(self, stop_loss, take_profits):
        exchange = BitgetDemoExchange(AppConfig())
        intent = type("Intent", (), {
            "symbol": "XAUUSDT",
            "side": "short",
            "order_type": "market",
            "entry_price": Decimal("4575"),
            "quantity": Decimal("0.27"),
            "stop_loss": stop_loss,
            "take_profits": take_profits,
        })()
        with patch.object(exchange, "_credential", return_value={"api_key": "k", "api_secret": "s", "passphrase": "p"}):
            with patch.object(exchange, "_request", return_value={"code": "00000", "data": []}) as request:
                exchange.place_position_tpsl(intent, "oid_2")
        return request.call_args.args[2] if request.called else {}


def _payload() -> dict:
    return {
        "symbol": "BTCUSDT",
        "hold_side": "long",
        "mode": "quantity",
        "quantity": 1,
        "order_type": "market",
        "price": None,
    }


if __name__ == "__main__":
    unittest.main()
