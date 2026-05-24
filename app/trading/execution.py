"""Trading execution orchestration."""

import uuid

from app.config import AppConfig
from app.exchanges.bitget import BitgetDemoExchange
from app.persistence.trading_store import TradingStore
from app.signals.models import SignalCandidate
from app.trading.risk import build_dry_run_intent
from app.trading.updates import build_update_intent


class TradingExecutor:
    def __init__(self, config: AppConfig, store: TradingStore):
        self._config = config
        self._store = store
        self._bitget = BitgetDemoExchange(config)

    def handle_candidate(
        self,
        candidate: SignalCandidate,
        message_time: str,
        persist: bool = True,
        ignore_stale: bool = False,
    ) -> dict:
        signal_id = self._store.save_candidate(candidate) if persist else ""
        update = self._handle_update(candidate, persist)
        if update:
            return {"signal_id": signal_id, **update, "intent": None, "order": None}
        intent = build_dry_run_intent(
            candidate,
            message_time,
            config=self._config.trading,
            ignore_stale=ignore_stale,
        )
        if not intent:
            return {"signal_id": signal_id, "intent": None, "order": None}
        execute = self._can_execute(intent)
        if execute:
            intent.dry_run = False
            intent.status = "ready"
        intent_id = self._store.save_intent(signal_id, intent) if persist else ""
        order = self._submit(intent, intent_id) if execute else self._dry_order(intent)
        if persist and order:
            self._store.save_order(intent_id, order)
        return {
            "signal_id": signal_id,
            "intent_id": intent_id,
            "intent": intent.to_dict(),
            "order": order,
        }

    def _handle_update(self, candidate: SignalCandidate, persist: bool) -> dict | None:
        if candidate.category != "position_update":
            return None
        related = self._store.find_signal_by_source_url(candidate.reply_url) if persist else ""
        update = build_update_intent(candidate, related)
        update_id = self._store.save_update(update) if persist and update else ""
        return {
            "update_id": update_id,
            "update": update.to_dict() if update else None,
        }

    def _can_execute(self, intent) -> bool:
        trading = self._config.trading
        if not trading.enabled or trading.execution_mode != "auto_demo":
            return False
        return intent.status == "ready" and not intent.reasons

    def _submit(self, intent, intent_id: str) -> dict:
        client_oid = self._client_oid(intent_id)
        try:
            return self._bitget.place_order(intent, client_oid)
        except Exception as exc:
            return {
                "exchange": "bitget",
                "status": "failed",
                "client_oid": client_oid,
                "order_id": "",
                "error": str(exc),
            }

    @staticmethod
    def _dry_order(intent) -> dict:
        return {
            "exchange": "bitget",
            "status": "dry_run" if intent.status == "ready" else "blocked",
            "client_oid": "",
            "order_id": "",
            "error": ",".join(intent.reasons),
        }

    @staticmethod
    def _client_oid(intent_id: str) -> str:
        base = intent_id.replace("intent_", "")[:20] if intent_id else uuid.uuid4().hex[:20]
        return f"kol_{base}"
