import unittest

from app.signals.models import SignalCandidate
from app.trading.execution import TradingExecutor
from app.trading.risk import build_dry_run_intents
from support import test_config


class MultiEntryRiskTests(unittest.TestCase):
    def test_more_sell_signal_builds_two_intents(self):
        intents = build_dry_run_intents(_candidate(), "2026-05-28 21:00:00", test_config().trading, ignore_stale=True)

        self.assertEqual(len(intents), 2)
        self.assertEqual([item.entry_price for item in intents], [4480.0, 4490.0])
        self.assertEqual(sum(item.quantity for item in intents), 0.27)
        self.assertTrue(all(item.layer_count == 2 for item in intents))


class MultiEntryExecutionTests(unittest.TestCase):
    def test_executor_submits_two_orders_for_two_entries(self):
        config = test_config()
        config.trading.enabled = True
        config.trading.execution_mode = "auto_demo"
        store = _StoreStub()
        executor = TradingExecutor(config, store)
        exchange = _ExchangeStub()
        executor._bitget = exchange

        result = executor.handle_candidate(_candidate(), "2026-05-28 21:00:00", persist=True, ignore_stale=True, allow_submit=True)

        self.assertEqual(len(result["intents"]), 2)
        self.assertEqual(len(result["orders"]), 2)
        self.assertEqual(result["order"]["status"], "submitted")
        self.assertEqual(store.intent_ids, ["intent_log_1_1", "intent_log_1_2"])
        self.assertEqual([item["entry_price"] for item in result["intents"]], [4480.0, 4490.0])
        self.assertEqual(len(set(exchange.client_oids)), 2)

    def test_client_oid_keeps_layered_orders_unique(self):
        first = TradingExecutor._client_oid("intent_1780917129356355152_0868_1")
        second = TradingExecutor._client_oid("intent_1780917129356355152_0868_2")

        self.assertNotEqual(first, second)
        self.assertLessEqual(len(first), 64)
        self.assertLessEqual(len(second), 64)


class _StoreStub:
    def __init__(self):
        self.intent_ids = []

    def save_candidate(self, candidate):
        return f"signal_{candidate.source_log_id}"

    def save_intent(self, signal_id, intent):
        intent_id = f"intent_{intent.source_log_id}_{intent.layer_index + 1}" if intent.layer_count > 1 else f"intent_{intent.source_log_id}"
        self.intent_ids.append(intent_id)
        return intent_id

    def save_order(self, intent_id, response):
        return f"order_{intent_id}"

    def find_signal_by_source_url(self, source_url):
        return ""

    def save_update(self, update):
        return f"update_{update.source_log_id}"


class _ExchangeStub:
    def __init__(self):
        self.calls = 0
        self.client_oids = []

    def get_market_price(self, symbol):
        return 0.0

    def place_order(self, intent, client_oid):
        self.calls += 1
        self.client_oids.append(client_oid)
        return {"exchange": "bitget", "status": "submitted", "client_oid": client_oid, "order_id": f"oid_{self.calls}"}

    def place_position_tpsl(self, intent, client_oid):
        return {"exchange": "bitget", "status": "submitted", "client_oid": client_oid, "order_id": ""}


def _candidate():
    return SignalCandidate(
        source_log_id="log_1",
        category="new_signal",
        raw_text="GOLD SELL NOW @ 4480 MORE SELL @ 4490 TP 4450 TP 4400 SL 4503",
        evidence_text="GOLD SELL NOW @ 4480 MORE SELL @ 4490",
        symbol="XAUUSD",
        bitget_symbol="XAUUSDT",
        side="short",
        entry_order_type="limit",
        entry_numbers=[4480.0, 4490.0],
        take_profits=[4450.0, 4400.0],
        stop_loss=4503.0,
        confidence=0.95,
        status="parsed",
    )


if __name__ == "__main__":
    unittest.main()
