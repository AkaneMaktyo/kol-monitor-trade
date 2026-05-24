"""Build account overview data for the UI."""

from app.config import AppConfig
from app.exchanges.bitget import BitgetDemoExchange
from app.persistence.account_store import AccountStore


class AccountOverviewService:
    def __init__(self, config: AppConfig, store: AccountStore):
        self._store = store
        self._exchange = BitgetDemoExchange(config)

    def load(self) -> dict:
        errors = []
        accounts = self._data(self._exchange.get_accounts(), errors, "accounts")
        positions = self._data(self._exchange.get_positions(), errors, "positions")
        orders = self._pending_orders(self._exchange.get_pending_orders(), errors)
        history = self._history_positions(self._exchange.get_history_positions(), errors)
        account = accounts[0] if accounts else {}
        if account:
            self._store.save_snapshot(account)
        return {
            "ok": not errors,
            "errors": errors,
            "summary": self._summary(account, positions, orders),
            "account": account,
            "curve": self._store.list_snapshots(),
            "positions": positions,
            "history_positions": history,
            "pending_orders": orders,
            "trade_orders": self._store.list_trade_orders(),
            "signal_updates": self._store.list_signal_updates(),
        }

    @staticmethod
    def _data(response: dict, errors: list[str], name: str) -> list[dict]:
        if response.get("code") != "00000":
            errors.append(f"{name}: {response.get('msg') or response.get('code')}")
            return []
        data = response.get("data") or []
        return data if isinstance(data, list) else []

    @staticmethod
    def _pending_orders(response: dict, errors: list[str]) -> list[dict]:
        if response.get("code") != "00000":
            errors.append(f"orders: {response.get('msg') or response.get('code')}")
            return []
        data = response.get("data") or {}
        return data.get("entrustedList") or []

    @staticmethod
    def _history_positions(response: dict, errors: list[str]) -> list[dict]:
        if response.get("code") != "00000":
            errors.append(f"history: {response.get('msg') or response.get('code')}")
            return []
        data = response.get("data") or {}
        return data.get("list") or []

    @staticmethod
    def _summary(account: dict, positions: list[dict], orders: list[dict]) -> dict:
        realized = sum(_num(item.get("achievedProfits")) for item in positions)
        margin = _num(account.get("crossedMargin")) + _num(account.get("isolatedMargin"))
        return {
            "equity": _num(account.get("accountEquity")),
            "available": _num(account.get("available")),
            "locked": _num(account.get("locked")),
            "unrealized_pl": _num(account.get("unrealizedPL")),
            "realized_pl": realized,
            "margin": margin,
            "risk_rate": _num(account.get("crossedRiskRate")),
            "positions": len(positions),
            "pending_orders": len(orders),
            "margin_coin": account.get("marginCoin", "USDT"),
        }


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
