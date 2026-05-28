"""Trading execution orchestration."""

import uuid

from app.config import AppConfig
from app.exchanges.bitget import BitgetDemoExchange
from app.persistence.trading_store import TradingStore
from app.signals.models import SignalCandidate
from app.trading.risk import build_dry_run_intents
from app.trading.updates import build_update_intent


class TradingExecutor:
    def __init__(self, config: AppConfig, store: TradingStore):
        self._config = config
        self._store = store
        self._bitget = BitgetDemoExchange(config)

    def handle_candidate(self, candidate: SignalCandidate, message_time: str, persist: bool = True, ignore_stale: bool = False, allow_submit: bool = True, audit: dict | None = None) -> dict:
        signal_id = self._store.save_candidate(candidate) if persist else ""
        update = self._handle_update(candidate, persist)
        if update:
            return {"signal_id": signal_id, **update, "intent": None, "order": None, "intents": [], "orders": []}
        intents = build_dry_run_intents(candidate, message_time, config=self._config.trading, ignore_stale=ignore_stale, market_price=self._market_price(candidate))
        if not intents:
            return {"signal_id": signal_id, "intent": None, "order": None, "intents": [], "orders": []}
        execute = self._can_execute(intents[0])
        intent_ids, payloads, orders = [], [], []
        for intent in intents:
            self._apply_audit(intent, audit)
            if execute and allow_submit:
                intent.dry_run = False
                intent.status = "ready"
            intent_id = self._store.save_intent(signal_id, intent) if persist else ""
            order = self._submit(intent, intent_id) if execute and allow_submit else self._dry_order(intent)
            if audit and order:
                order.update(audit)
            if persist and order:
                self._store.save_order(intent_id, order)
            intent_ids.append(intent_id)
            payloads.append(intent.to_dict())
            orders.append(order)
        return {
            "signal_id": signal_id,
            "intent_id": intent_ids[0] if intent_ids else "",
            "intent_ids": intent_ids,
            "intent": payloads[0] if payloads else None,
            "intents": payloads,
            "order": _primary_order(orders),
            "orders": orders,
        }

    def _handle_update(self, candidate: SignalCandidate, persist: bool) -> dict | None:
        if candidate.category != "position_update":
            return None
        related = self._store.find_signal_by_source_url(candidate.reply_url) if persist else ""
        update = build_update_intent(candidate, related)
        update_id = self._store.save_update(update) if persist and update else ""
        return {"update_id": update_id, "update": update.to_dict() if update else None}

    def _can_execute(self, intent) -> bool:
        trading = self._config.trading
        return bool(trading.enabled and trading.execution_mode == "auto_demo" and intent.status == "ready" and not intent.reasons)

    def _market_price(self, candidate: SignalCandidate) -> float:
        if candidate.category != "new_signal" or candidate.entry_numbers or candidate.entry_order_type != "market" or not candidate.bitget_symbol:
            return 0.0
        try:
            return self._bitget.get_market_price(candidate.bitget_symbol)
        except Exception:
            return 0.0

    def _submit(self, intent, intent_id: str) -> dict:
        client_oid = self._client_oid(intent_id)
        try:
            return self._bitget.place_order(intent, client_oid)
        except Exception as exc:
            return {"exchange": "bitget", "status": "failed", "client_oid": client_oid, "order_id": "", "error": str(exc)}

    @staticmethod
    def _dry_order(intent) -> dict:
        return {"exchange": "bitget", "status": "dry_run" if intent.status == "ready" else "blocked", "client_oid": "", "order_id": "", "error": ",".join(intent.reasons)}

    @staticmethod
    def _client_oid(intent_id: str) -> str:
        base = intent_id.replace("intent_", "")[:20] if intent_id else uuid.uuid4().hex[:20]
        return f"kol_{base}"

    @staticmethod
    def _apply_audit(intent, audit: dict | None) -> None:
        if not audit:
            return
        intent.origin = audit.get("origin", "")
        intent.origin_log_id = audit.get("origin_log_id", "")
        intent.triggered_at = audit.get("triggered_at", "")


def _primary_order(orders: list[dict]) -> dict | None:
    if not orders:
        return None
    if len(orders) == 1:
        return orders[0]
    merged = dict(orders[0])
    merged["status"] = _status(orders)
    merged["order_id"] = ",".join(item.get("order_id", "") for item in orders if item.get("order_id"))
    merged["error"] = ",".join(item.get("error", "") for item in orders if item.get("error"))
    merged["order_count"] = len(orders)
    return merged


def _status(orders: list[dict]) -> str:
    statuses = [item.get("status", "") for item in orders]
    if any(status == "failed" for status in statuses):
        return "failed"
    if all(status == "submitted" for status in statuses):
        return "submitted"
    if all(status == "dry_run" for status in statuses):
        return "dry_run"
    if all(status == "blocked" for status in statuses):
        return "blocked"
    return statuses[0] if statuses else ""
