import unittest
from unittest.mock import AsyncMock, patch

from app.config import AppConfig
from app.services.replay.action_service import ReplayActionService
from app.services.replay.query_service import ReplayQueryService, clear_replay_query_cache
from app.signals.models import SignalCandidate
from app.trading.execution import TradingExecutor


class TradingExecutorReplayTests(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig()
        self.config.trading.enabled = True
        self.config.trading.execution_mode = "auto_demo"
        self.store = _StoreStub()
        self.executor = TradingExecutor(self.config, self.store)
        self.executor._bitget = _ExchangeStub()

    def test_allow_submit_false_keeps_dry_run_and_audit(self):
        result = self.executor.handle_candidate(
            _candidate(),
            "2026-05-27 10:00:00",
            persist=False,
            ignore_stale=True,
            allow_submit=False,
            audit=_audit(),
        )
        self.assertEqual(result["order"]["status"], "dry_run")
        self.assertTrue(result["intent"]["dry_run"])
        self.assertEqual(result["intent"]["origin"], "replay_manual")
        self.assertEqual(result["order"]["origin_log_id"], "log_1")

    def test_allow_submit_true_uses_real_submit_and_keeps_audit(self):
        result = self.executor.handle_candidate(
            _candidate(),
            "2026-05-27 10:00:00",
            persist=False,
            ignore_stale=True,
            allow_submit=True,
            audit=_audit(),
        )
        self.assertEqual(result["order"]["status"], "submitted")
        self.assertFalse(result["intent"]["dry_run"])
        self.assertEqual(result["intent"]["triggered_at"], "2026-05-27 10:01:02")


class ReplayActionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_execute_requires_confirmation_text(self):
        service = ReplayActionService(AppConfig(), _ReplayStoreStub([]), executor=None)
        with self.assertRaisesRegex(ValueError, "REAL_EXECUTE"):
            await service.run_gold_empire("real_execute", ["a"], "")

    async def test_real_execute_stops_on_failed_submission(self):
        rows = [_row("a"), _row("b")]
        service = ReplayActionService(AppConfig(), _ReplayStoreStub(rows), executor=None)
        ready = _item("submitted", real_execute=True)
        failed = _item("failed", real_execute=True)
        with patch("app.services.replay.action_service.build_live_context", return_value={"live_mode": True}):
            with patch(
                "app.services.replay.action_service.inspect_log",
                new=AsyncMock(side_effect=[ready, ready, ready, failed]),
            ):
                result = await service.run_gold_empire("real_execute", ["a", "b"], "REAL_EXECUTE")
        self.assertFalse(result["ok"])
        self.assertEqual(result["stopped_at"], 2)
        self.assertEqual(result["results"][0]["execution_status"], "submitted")
        self.assertEqual(result["results"][1]["execution_status"], "failed")

    async def test_persist_clears_replay_query_cache(self):
        service = ReplayActionService(AppConfig(), _ReplayStoreStub([_gold_row("a")]), executor=None)
        with patch("app.services.replay.action_service.build_live_context", return_value={"live_mode": False}):
            with patch("app.services.replay.action_service.inspect_log", new=AsyncMock(return_value=_item("blocked", False))):
                with patch("app.services.replay.action_service.clear_replay_query_cache") as clear_cache:
                    await service.run_gold_empire("persist", ["a"], "")
        clear_cache.assert_called_once()


class ReplayQueryCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        clear_replay_query_cache()

    async def test_same_filter_uses_query_cache(self):
        service = ReplayQueryService(AppConfig(), _RecentStoreStub([_gold_row("a")]), executor=None)
        with patch("app.services.replay.query_service.build_live_context", return_value={"live_mode": False}):
            with patch("app.services.replay.query_service.inspect_log", new=AsyncMock(return_value=_item("parsed", False))) as inspect:
                await service.load_gold_empire(limit=1)
                await service.load_gold_empire(limit=1)
        self.assertEqual(inspect.await_count, 1)


class _StoreStub:
    def save_candidate(self, candidate):
        return f"signal_{candidate.source_log_id}"

    def save_intent(self, signal_id, intent):
        return f"intent_{intent.source_log_id}"

    def save_order(self, intent_id, response):
        return f"order_{intent_id}"

    def find_signal_by_source_url(self, source_url):
        return ""

    def save_update(self, update):
        return f"update_{update.source_log_id}"


class _ExchangeStub:
    def get_market_price(self, symbol):
        return 0.0

    def place_order(self, intent, client_oid):
        return {"exchange": "bitget", "status": "submitted", "client_oid": client_oid, "order_id": "oid_1"}


class _ReplayStoreStub:
    def __init__(self, rows):
        self._rows = rows

    def logs_by_ids(self, log_ids):
        mapping = {row["id"]: row for row in self._rows}
        return [mapping[item] for item in log_ids if item in mapping]


class _RecentStoreStub:
    def __init__(self, rows):
        self._rows = rows

    def recent_wxpusher(self, limit, author, source_channel):
        return list(self._rows)


def _candidate():
    return SignalCandidate(
        source_log_id="log_1",
        category="new_signal",
        raw_text="GOLD BUY",
        evidence_text="GOLD BUY 4500",
        symbol="XAUUSD",
        bitget_symbol="XAUUSDT",
        side="long",
        entry_order_type="limit",
        entry_numbers=[4500.0],
        take_profits=[4520.0],
        stop_loss=4490.0,
        confidence=0.95,
        status="parsed",
    )


def _audit():
    return {"origin": "replay_manual", "origin_log_id": "log_1", "triggered_at": "2026-05-27 10:01:02"}


def _row(log_id):
    return {"id": log_id, "content": "PREMIUM SIGNALS GOLD", "timestamp": "2026-05-27 10:00:00"}


def _gold_row(log_id):
    return {
        "id": log_id,
        "content": "PREMIUM SIGNALS GOLD\n閸樼喐鏋?: https://example.com/" + log_id,
        "timestamp": "2026-05-27 10:00:00",
        "author": "Gold Empire",
        "source_channel": "smoke",
    }


def _item(status, real_execute):
    return {
        "log_id": "x",
        "candidate": {"status": "parsed"},
        "execution": {"status": status},
        "selectable_actions": {
            "real_execute": real_execute,
            "real_execute_disabled_reason": "",
            "batch_selectable": True,
        },
    }


if __name__ == "__main__":
    unittest.main()
