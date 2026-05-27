"""Build the dashboard trading board snapshot."""

import json

from app.config import AppConfig
from app.exchanges.bitget import BitgetDemoExchange
from app.persistence.signal_board_store import SignalBoardStore
from app.trading.risk import describe_risk_budget


class TradingBoardService:
    def __init__(self, config: AppConfig, store: SignalBoardStore):
        self._config = config
        self._store = store
        self._exchange = BitgetDemoExchange(config)

    def load(self, limit: int = 6) -> dict:
        rows = self._store.snapshot(limit)
        orders = [self._order(row) for row in rows["orders"]]
        return {
            "readiness": self._readiness(orders[0] if orders else None),
            "signals": {
                "ready": [self._signal(row) for row in rows["ready"]],
                "review": [self._signal(row) for row in rows["review"]],
                "updates": [self._update(row) for row in rows["updates"]],
                "orders": orders,
            },
        }

    def _readiness(self, last_order: dict | None) -> dict:
        trading = self._config.trading
        budget = describe_risk_budget(trading)
        credential = self._exchange.credential_status()
        live_mode = bool(
            trading.enabled
            and trading.execution_mode == "auto_demo"
            and credential["ok"]
        )
        return {
            "trading_enabled": trading.enabled,
            "execution_mode": trading.execution_mode,
            "credential_status": "ready" if credential["ok"] else "missing",
            "credential_message": credential["error"] or "已找到 Bitget demo 凭证",
            "risk_budget": budget,
            "max_signal_age_seconds": trading.max_signal_age_seconds,
            "product_type": trading.product_type,
            "proxy_enabled": bool(trading.proxy_url.strip()),
            "live_mode": live_mode,
            "last_order": last_order,
        }

    def _signal(self, row: dict) -> dict:
        parsed = _object(row.get("parsed_json"))
        request = _object(row.get("request_json"))
        reasons = _list(row.get("reasons_json"))
        return {
            "source_log_id": row.get("source_log_id", ""),
            "symbol": row.get("symbol") or parsed.get("symbol") or parsed.get("bitget_symbol") or "--",
            "side": row.get("side") or parsed.get("side") or "",
            "summary": parsed.get("evidence_text") or _summary(row.get("raw_text", "")),
            "status": row.get("intent_status") or row.get("candidate_status") or parsed.get("status") or "",
            "order_status": row.get("order_status", ""),
            "order_type": row.get("order_type") or parsed.get("entry_order_type") or "",
            "entry_price": row.get("price") or request.get("entry_price") or 0,
            "quantity": row.get("quantity") or request.get("quantity") or 0,
            "missing_fields": parsed.get("missing_fields") or [],
            "reasons": reasons,
            "risk_percent": request.get("risk_percent") or 0,
            "quote_risk_usdt": request.get("quote_risk_usdt") or 0,
            "updated_at": row.get("updated_at") or row.get("created_at") or "",
        }

    def _update(self, row: dict) -> dict:
        request = _object(row.get("request_json"))
        return {
            "source_log_id": row.get("source_log_id", ""),
            "related_signal_id": row.get("related_signal_id", ""),
            "symbol": row.get("symbol") or "--",
            "side": row.get("side") or "",
            "action": row.get("action", ""),
            "summary": request.get("action_text") or ",".join(request.get("actions") or []) or row.get("action", ""),
            "close_fraction": row.get("close_fraction") or 0,
            "status": row.get("status", ""),
            "reasons": _list(row.get("reasons_json")),
            "updated_at": row.get("updated_at", ""),
        }

    def _order(self, row: dict) -> dict:
        request = _object(row.get("request_json"))
        return {
            "source_log_id": row.get("source_log_id", ""),
            "symbol": row.get("symbol") or "--",
            "side": row.get("side") or "",
            "order_type": row.get("order_type") or request.get("order_type") or "",
            "entry_price": row.get("price") or request.get("entry_price") or 0,
            "quantity": row.get("quantity") or request.get("quantity") or 0,
            "intent_status": row.get("intent_status", ""),
            "status": row.get("order_status", ""),
            "exchange_order_id": row.get("exchange_order_id", ""),
            "error_message": row.get("error_message", ""),
            "updated_at": row.get("updated_at", ""),
        }


def _object(value: str | None) -> dict:
    try:
        data = json.loads(value) if value else {}
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _list(value: str | None) -> list:
    try:
        data = json.loads(value) if value else []
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _summary(text: str) -> str:
    return " ".join(str(text or "").split())[:180]
