"""Build account overview data for the UI."""

from concurrent.futures import ThreadPoolExecutor

from app.config import AppConfig
from app.exchanges.bitget import BitgetDemoExchange
from app.persistence.account_store import AccountStore


class AccountOverviewService:
    def __init__(self, config: AppConfig, store: AccountStore):
        self._store = store
        self._exchange = BitgetDemoExchange(config)

    def load(self) -> dict:
        current = self.load_current()
        history = self.load_history()
        current["ok"] = current["ok"] and history["ok"]
        current["errors"] = [*current["errors"], *history["errors"]]
        current["history_positions"] = history["history_positions"]
        return current

    def load_current(self, save_snapshot: bool = True) -> dict:
        errors = []
        responses = self._responses(errors)
        accounts = self._data(responses["accounts"], errors, "accounts")
        positions = self._data(responses["positions"], errors, "positions")
        orders = self._pending_orders(responses["orders"], errors)
        account = accounts[0] if accounts else {}
        if account and save_snapshot:
            self._store.save_snapshot(account)
        return {
            "ok": not errors,
            "errors": errors,
            "summary": self._summary(account, positions, orders),
            "account": account,
            "curve": self._store.list_snapshots(),
            "positions": positions,
            "pending_orders": orders,
            "trade_orders": self._store.list_trade_orders(),
            "signal_updates": self._store.list_signal_updates(),
        }

    def load_history(self) -> dict:
        errors = []
        history = self._history_positions(self._exchange.get_history_positions(), errors)
        return {
            "ok": not errors,
            "errors": errors,
            "history_positions": history,
        }

    def _responses(self, errors: list[str]) -> dict[str, dict]:
        calls = {
            "accounts": self._exchange.get_accounts,
            "positions": self._exchange.get_positions,
            "orders": self._exchange.get_pending_orders,
        }
        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            futures = {name: pool.submit(call) for name, call in calls.items()}
        responses = {}
        for name, future in futures.items():
            try:
                responses[name] = future.result()
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                responses[name] = {}
        return responses

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
