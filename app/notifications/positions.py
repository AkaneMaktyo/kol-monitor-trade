"""Watch Bitget positions and notify on real position changes."""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.config import AppConfig
from app.exchanges.bitget import BitgetDemoExchange
from app.notifications.wxpusher import WxPusherNotifier

logger = logging.getLogger(__name__)
WATCH_FIELDS = ("total", "available", "open_price", "leverage")


class PositionWatcher:
    def __init__(self, config: AppConfig):
        self._config = config
        self._exchange = BitgetDemoExchange(config)
        self._notifier = WxPusherNotifier(config.position_notify)
        self._last: dict[str, dict] | None = None

    async def run(self) -> None:
        notify = self._config.position_notify
        if not notify.enabled:
            return
        if notify.channel != "wxpusher":
            logger.warning("unsupported position notify channel: %s", notify.channel)
            return
        if not self._notifier.ready:
            logger.warning("position notify enabled, but WxPusher is not configured")
            return
        logger.info("position watcher started, interval=%ss", notify.interval_seconds)
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("position watcher poll failed")
            await asyncio.sleep(notify.interval_seconds)

    async def check_once(self) -> list[str]:
        response = await asyncio.to_thread(self._exchange.get_positions)
        if response.get("code") != "00000":
            logger.warning("read positions failed: %s", response.get("msg") or response)
            return []
        current = _snapshot(response.get("data") or [])
        if self._last is None:
            self._last = current
            logger.info("position watcher baseline loaded: %s positions", len(current))
            return []
        changes = _diff(self._last, current)
        if changes:
            text = _message(changes, self._last, current)
            result = await self._notifier.send("仓位变动提醒", text)
            if not result.ok:
                logger.warning("position notification failed: %s", result.error)
            else:
                logger.info("position notification sent: %s changes", len(changes))
        self._last = current
        return changes


def _snapshot(rows: list[dict]) -> dict[str, dict]:
    snapshot = {}
    for row in rows:
        total = _num(row.get("total"))
        if total == "0":
            continue
        symbol = str(row.get("symbol") or "").upper()
        side = str(row.get("holdSide") or row.get("posSide") or row.get("side") or "")
        if not symbol or not side:
            continue
        key = f"{symbol}:{side.lower()}"
        snapshot[key] = {
            "symbol": symbol,
            "side": side.lower(),
            "total": total,
            "available": _num(row.get("available")),
            "open_price": _num(row.get("averageOpenPrice") or row.get("openPrice")),
            "leverage": _num(row.get("leverage")),
            "unrealized_pl": _num(row.get("unrealizedPL")),
        }
    return snapshot


def _diff(before: dict[str, dict], after: dict[str, dict]) -> list[str]:
    changes = []
    for key in sorted(after.keys() - before.keys()):
        changes.append(f"新增 {_format(after[key])}")
    for key in sorted(before.keys() - after.keys()):
        changes.append(f"移除 {_format(before[key])}")
    for key in sorted(before.keys() & after.keys()):
        fields = [
            f"{_label(name)} {before[key][name]} -> {after[key][name]}"
            for name in WATCH_FIELDS
            if before[key][name] != after[key][name]
        ]
        if fields:
            changes.append(f"更新 {_format(after[key])}: " + "，".join(fields))
    return changes


def _message(changes: list[str], before: dict[str, dict], after: dict[str, dict]) -> str:
    lines = [
        "仓位变动提醒",
        f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"变动数: {len(changes)}",
        "",
        *[f"- {item}" for item in changes],
        "",
        f"当前持仓: {len(after)} 个，变动前: {len(before)} 个",
    ]
    return "\n".join(lines)


def _format(row: dict) -> str:
    side = {"long": "多", "short": "空"}.get(row["side"], row["side"])
    return (
        f"{row['symbol']} {side} 数量 {row['total']} "
        f"均价 {row['open_price']} 浮盈 {row['unrealized_pl']}"
    )


def _label(name: str) -> str:
    return {
        "total": "数量",
        "available": "可平",
        "open_price": "均价",
        "leverage": "杠杆",
    }[name]


def _num(value) -> str:
    try:
        decimal = Decimal(str(value or "0")).normalize()
    except (InvalidOperation, ValueError):
        return "0"
    return format(decimal, "f")
