import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.exchanges.bitget import BitgetDemoExchange
from app.routes import account
from app.services.account_overview import AccountOverviewService
from support import test_config


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
        exchange = BitgetDemoExchange(test_config())
        with patch.object(exchange, "_request", return_value={"code": "00000", "data": {}}) as request:
            exchange.close_position("BTCUSDT", "long", Decimal("1.25"), "oid_1", order_type=order_type, price=price)
        return request.call_args.args[2]


class ClosePositionRouteTests(unittest.TestCase):
    def test_internal_error_returns_json_detail(self):
        app = FastAPI()
        app.state.config = test_config()
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
        exchange = BitgetDemoExchange(test_config())
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


class AccountOverviewServiceTests(unittest.TestCase):
    def test_load_merges_account_sections(self):
        store = _FakeAccountStore()
        service = AccountOverviewService(test_config(), store)
        service._exchange = _FakeExchange()

        payload = service.load()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"]["positions"], 1)
        self.assertEqual(payload["summary"]["pending_orders"], 1)
        self.assertEqual(payload["curve"], [{"account_equity": 1000.0}])
        self.assertEqual(store.saved["accountEquity"], "1000")
        self.assertEqual(payload["history_positions"], [{"symbol": "XAUUSDT"}])

    def test_load_collects_exchange_errors(self):
        service = AccountOverviewService(test_config(), _FakeAccountStore())
        service._exchange = _ErrorExchange()

        payload = service.load()

        self.assertFalse(payload["ok"])
        self.assertIn("positions: timeout", payload["errors"])
        self.assertEqual(payload["positions"], [])
        self.assertEqual(payload["pending_orders"], [])

    def test_load_history_separates_slow_section(self):
        service = AccountOverviewService(test_config(), _FakeAccountStore())
        service._exchange = _FakeExchange()
        payload = service.load_history()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["history_positions"], [{"symbol": "XAUUSDT"}])


def _payload() -> dict:
    return {
        "symbol": "BTCUSDT",
        "hold_side": "long",
        "mode": "quantity",
        "quantity": 1,
        "order_type": "market",
        "price": None,
    }


class _FakeExchange:
    def get_accounts(self):
        return {"code": "00000", "data": [{"accountEquity": "1000", "available": "850", "marginCoin": "USDT"}]}

    def get_positions(self):
        return {"code": "00000", "data": [{"symbol": "XAUUSDT", "achievedProfits": "12.5"}]}

    def get_pending_orders(self):
        return {"code": "00000", "data": {"entrustedList": [{"orderId": "oid_1"}]}}

    def get_history_positions(self):
        return {"code": "00000", "data": {"list": [{"symbol": "XAUUSDT"}]}}


class _ErrorExchange(_FakeExchange):
    def get_positions(self):
        raise RuntimeError("timeout")

    def get_pending_orders(self):
        return {"code": "50001", "msg": "busy"}

    def get_history_positions(self):
        return {"code": "50002", "msg": "history busy"}


class _FakeAccountStore:
    def __init__(self):
        self.saved = {}

    def save_snapshot(self, account: dict):
        self.saved = account

    def list_snapshots(self):
        return [{"account_equity": 1000.0}]

    def list_trade_orders(self):
        return []

    def list_signal_updates(self):
        return []


if __name__ == "__main__":
    unittest.main()
