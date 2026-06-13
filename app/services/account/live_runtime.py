"""Live account refresh runtime."""

import asyncio
import json
import logging
import time

import websockets

from app.exchanges.bitget import BitgetDemoExchange
from app.exchanges.bitget_support import signature
from app.services.account_overview import AccountOverviewService
from app.websocket_manager import ConnectionManager

logger = logging.getLogger(__name__)

PRIVATE_WS_URL = "wss://wspap.bitget.com/v2/ws/private"
WATCHED_CHANNELS = ("account", "positions", "orders", "fill")
CURRENT_INTERVAL_SECONDS = 6
SNAPSHOT_INTERVAL_SECONDS = 30
PING_INTERVAL_SECONDS = 25
EVENT_REFRESH_GAP_SECONDS = 1.5


class AccountLiveRuntime:
    def __init__(self, config, store, ws_manager: ConnectionManager):
        self._config = config
        self._service = AccountOverviewService(config, store)
        self._exchange = BitgetDemoExchange(config)
        self._ws_manager = ws_manager
        self._current = None
        self._tasks: list[asyncio.Task] = []
        self._refresh_task: asyncio.Task | None = None
        self._refresh_lock = asyncio.Lock()
        self._last_refresh = 0.0
        self._last_snapshot = 0.0
        self._pending_reason = "boot"
        self._pending_history = False

    async def start(self) -> None:
        try:
            await self.refresh("boot", history_hint=True, force_snapshot=True)
        except Exception as exc:
            logger.warning("account boot refresh failed: %s", exc)
        self._tasks = [
            asyncio.create_task(self._timer_loop()),
            asyncio.create_task(self._private_ws_loop()),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._refresh_task:
            self._refresh_task.cancel()
            self._tasks.append(self._refresh_task)
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def snapshot(self) -> dict:
        if self._current is None:
            await self.refresh("demand", history_hint=True, force_snapshot=True)
        return self._current or {}

    async def refresh(
        self,
        reason: str,
        *,
        history_hint: bool = False,
        force_snapshot: bool = False,
    ) -> None:
        async with self._refresh_lock:
            save_snapshot = force_snapshot or self._snapshot_due()
            payload = await asyncio.to_thread(self._service.load_current, save_snapshot)
            now = time.monotonic()
            self._current = payload
            self._last_refresh = now
            if save_snapshot:
                self._last_snapshot = now
        await self._ws_manager.broadcast({
            "type": "account_current",
            "data": {"reason": reason, "history_hint": history_hint, "payload": payload},
        })

    async def schedule_refresh(self, reason: str, *, history_hint: bool) -> None:
        self._pending_reason = reason
        self._pending_history = self._pending_history or history_hint
        if self._refresh_task and not self._refresh_task.done():
            return
        delay = max(0.0, EVENT_REFRESH_GAP_SECONDS - (time.monotonic() - self._last_refresh))
        self._refresh_task = asyncio.create_task(self._delayed_refresh(delay))

    async def _delayed_refresh(self, delay: float) -> None:
        if delay:
            await asyncio.sleep(delay)
        reason = self._pending_reason
        history_hint = self._pending_history
        self._pending_reason = "event"
        self._pending_history = False
        await self.refresh(reason, history_hint=history_hint)

    async def _timer_loop(self) -> None:
        while True:
            await asyncio.sleep(CURRENT_INTERVAL_SECONDS)
            await self.refresh("timer")

    async def _private_ws_loop(self) -> None:
        delay = 2
        while True:
            try:
                await self._stream_private()
                delay = 2
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("bitget private ws disconnected: %s", exc)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    async def _stream_private(self) -> None:
        proxy = self._config.trading.proxy_url.strip() or None
        async with websockets.connect(PRIVATE_WS_URL, ping_interval=None, proxy=proxy) as socket:
            await self._login(socket)
            await self._subscribe(socket)
            ping_task = asyncio.create_task(self._ping_loop(socket))
            try:
                while True:
                    raw = await socket.recv()
                    if raw == "pong":
                        continue
                    await self._handle_message(raw)
            finally:
                ping_task.cancel()
                await asyncio.gather(ping_task, return_exceptions=True)

    async def _login(self, socket) -> None:
        credential = self._exchange._credential()
        timestamp = str(int(time.time()))
        sign = signature(credential["api_secret"], timestamp, "GET", "/user/verify", "")
        await socket.send(json.dumps({
            "op": "login",
            "args": [{
                "apiKey": credential["api_key"],
                "passphrase": credential["passphrase"],
                "timestamp": timestamp,
                "sign": sign,
            }],
        }))
        payload = json.loads(await socket.recv())
        if str(payload.get("event")) != "login" or str(payload.get("code")) not in {"0", ""}:
            raise RuntimeError(payload.get("msg") or payload)

    async def _subscribe(self, socket) -> None:
        args = [{"instType": "default", "channel": channel, "coin": "default"} for channel in WATCHED_CHANNELS]
        await socket.send(json.dumps({"op": "subscribe", "args": args}))

    async def _ping_loop(self, socket) -> None:
        while True:
            await asyncio.sleep(PING_INTERVAL_SECONDS)
            await socket.send("ping")

    async def _handle_message(self, raw: str) -> None:
        payload = json.loads(raw)
        if payload.get("event") in {"subscribe"}:
            return
        channel = str((payload.get("arg") or {}).get("channel") or "")
        if channel not in WATCHED_CHANNELS:
            return
        await self.schedule_refresh(channel, history_hint=channel in {"positions", "orders", "fill"})

    def _snapshot_due(self) -> bool:
        return time.monotonic() - self._last_snapshot >= SNAPSHOT_INTERVAL_SECONDS
