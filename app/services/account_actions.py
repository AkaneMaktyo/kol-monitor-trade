"""Account-level trading actions."""

from decimal import Decimal, ROUND_DOWN
import time

from app.config import AppConfig
from app.exchanges.bitget import BitgetDemoExchange


class AccountActionService:
    def __init__(self, config: AppConfig):
        self._exchange = BitgetDemoExchange(config)

    def close_position(self, payload: dict) -> dict:
        symbol = str(payload.get("symbol") or "").upper()
        side = _side(payload.get("hold_side"))
        position = self._find_position(symbol, side)
        total = _decimal(position.get("total"))
        size = _close_size(payload, total)
        client_oid = f"kmt_close_{int(time.time() * 1000)}"
        order = self._exchange.close_position(symbol, side, size, client_oid)
        return {
            "ok": order.get("status") == "submitted",
            "order": order,
            "request": {
                "symbol": symbol,
                "hold_side": side,
                "size": _format_decimal(size),
                "total": _format_decimal(total),
            },
        }

    def _find_position(self, symbol: str, side: str) -> dict:
        response = self._exchange.get_positions()
        if response.get("code") != "00000":
            raise ValueError(response.get("msg") or response.get("code") or "仓位读取失败")
        for row in response.get("data") or []:
            row_side = _side(row.get("holdSide") or row.get("posSide") or row.get("side"))
            if str(row.get("symbol", "")).upper() == symbol and row_side == side:
                if _decimal(row.get("total")) > 0:
                    return row
        raise ValueError("未找到可平仓位")


def _close_size(payload: dict, total: Decimal) -> Decimal:
    if total <= 0:
        raise ValueError("仓位数量无效")
    mode = str(payload.get("mode") or "")
    if mode == "quantity":
        size = _decimal(payload.get("quantity"))
    elif mode == "percent":
        percent = _decimal(payload.get("percent"))
        if percent <= 0 or percent > 100:
            raise ValueError("平仓比例需在 0-100 之间")
        size = total if percent == 100 else _floor(total * percent / Decimal("100"), _scale(total))
    else:
        raise ValueError("平仓方式无效")
    if size <= 0:
        raise ValueError("平仓数量需大于 0")
    if size > total:
        raise ValueError("平仓数量不能超过当前仓位")
    return size


def _side(value) -> str:
    normalized = str(value or "").lower()
    if normalized in {"long", "buy"}:
        return "long"
    if normalized in {"short", "sell"}:
        return "short"
    raise ValueError("仓位方向无效")


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception as exc:
        raise ValueError("数量格式无效") from exc


def _scale(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    return abs(exponent) if exponent < 0 else 0


def _floor(value: Decimal, scale: int) -> Decimal:
    quantum = Decimal("1").scaleb(-scale)
    return value.quantize(quantum, rounding=ROUND_DOWN)


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")
