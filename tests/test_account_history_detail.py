import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.persistence.account_store import _pick_candidates
from app.routes import account


class HistoryLifecycleMatchTests(unittest.TestCase):
    def test_pick_candidates_prefers_quantity_fit(self):
        rows = [
            {"signal_id": "a", "price": 4528, "quantity": 0.35, "order_status": "submitted"},
            {"signal_id": "b", "price": 4575, "quantity": 0.27, "order_status": "dry_run"},
        ]
        matched = _pick_candidates(rows, target_price=4540.78, target_size=0.35)
        self.assertEqual([row["signal_id"] for row in matched], ["a"])

    def test_pick_candidates_can_merge_multiple_open_legs(self):
        rows = [
            {"signal_id": "a", "price": 4510, "quantity": 0.17, "order_status": "submitted"},
            {"signal_id": "b", "price": 4510, "quantity": 0.17, "order_status": "dry_run"},
        ]
        matched = _pick_candidates(rows, target_price=4510, target_size=0.34)
        self.assertEqual({row["signal_id"] for row in matched}, {"a", "b"})


class HistoryDetailRouteTests(unittest.TestCase):
    def test_history_detail_renders_timeline(self):
        app = FastAPI()
        app.state.account_store = _FakeStore()
        app.include_router(account.router)
        response = TestClient(app).get(
            "/api/account/history-detail",
            params={
                "symbol": "XAUUSDT",
                "hold_side": "short",
                "closed_at": 1779722259951,
                "open_price": 4540.78,
                "open_size": 0.35,
                "close_price": 4574.7,
                "net_profit": -11.57,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("生命周期", body["title"])
        self.assertIn("history-summary-grid", body["html"])
        self.assertIn("history-timeline", body["html"])
        self.assertIn("查看原始内容", body["html"])
        self.assertIn("开仓信号", body["html"])
        self.assertIn("仓位更新", body["html"])
        self.assertIn("止盈", body["html"])
        self.assertIn("止损", body["html"])


class _FakeStore:
    def get_history_lifecycle(self, **kwargs):
        return {
            "pool_size": 2,
            "matched_size": 1,
            "signals": [{
                "source_log_id": "log_open",
                "signal_id": "signal_open",
                "signal_time": "2026-05-25 13:58:50",
                "platform": "telegram",
                "author": "Gold Empire",
                "source_channel": "vip",
                "content": "SELL NOW @ 4528",
                "price": 4528,
                "quantity": 0.35,
                "order_type": "market",
                "intent_status": "ready",
                "order_status": "submitted",
                "exchange_order_id": "oid_1",
                "parsed_json": {"evidence_text": "黄金空单", "take_profits": [4514, 4490], "stop_loss": 4542},
            }],
            "updates": [{
                "source_log_id": "log_close",
                "updated_at": "2026-05-25 22:50:16",
                "platform": "telegram",
                "author": "Gold Empire",
                "source_channel": "vip",
                "content": "close full",
                "action": "close",
                "status": "ready",
                "close_fraction": 1,
            }],
        }


if __name__ == "__main__":
    unittest.main()
