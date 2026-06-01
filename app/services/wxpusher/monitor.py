import asyncio
import json
from contextlib import suppress
from typing import Awaitable, Callable, Optional

import websockets

from app.config import AppConfig
from app.models import ConnectionStatus, LogEntry, PlatformConnectionState, app_now
from app.services.wxpusher.client import WxPusherApiError, WxPusherClient, WxPusherLoginRequired
from app.services.wxpusher.normalizer import MessageDeduplicator, polling_entry, polling_sort_key, websocket_entry
from app.services.wxpusher.shared import SharedWxPusherRuntime

OnMessage = Callable[[LogEntry], Awaitable[None]]
RECONNECT_DELAYS = (5, 10, 15, 30, 60, 120)


class WxPusherMonitor:
    def __init__(
        self,
        config: AppConfig,
        state: PlatformConnectionState,
        shared_runtime: SharedWxPusherRuntime,
    ):
        self._config = config.wxpusher
        self._state = state
        self._client = WxPusherClient(self._config)
        self._shared_runtime = shared_runtime
        self._on_message: Optional[OnMessage] = None
        self._tasks: list[asyncio.Task] = []
        self._dedupe = MessageDeduplicator()
        self._stop_requested = False

    @property
    def is_connected(self) -> bool:
        return self._state.status == ConnectionStatus.CONNECTED

    async def start(self, on_message: OnMessage) -> None:
        self._on_message = on_message
        self._stop_requested = False
        self._shared_runtime.initialize()
        self._sync_channels()
        self._state.status = ConnectionStatus.RECONNECTING
        self._tasks = [
            asyncio.create_task(self._polling_loop()),
            asyncio.create_task(self._websocket_loop()),
        ]

    async def stop(self) -> None:
        self._stop_requested = True
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        self._state.status = ConnectionStatus.DISCONNECTED

    async def _polling_loop(self) -> None:
        while not self._stop_requested:
            try:
                self._refresh_settings()
                if not self._config.enable_polling:
                    await asyncio.sleep(10)
                    continue
                if not self._config.device_token:
                    self._mark_error("WXPUSHER_DEVICE_TOKEN missing")
                    await asyncio.sleep(10)
                    continue
                await self._poll_once()
                self._mark_connected()
            except WxPusherLoginRequired as exc:
                self._mark_error(str(exc))
            except (WxPusherApiError, OSError, TimeoutError) as exc:
                self._mark_reconnecting(f"REST polling failed: {exc}")
            await asyncio.sleep(self._config.poll_interval_seconds)

    async def _poll_once(self) -> None:
        messages = await self._client.fetch_latest()
        for item in sorted(messages, key=polling_sort_key):
            self._shared_runtime.save_message("polling", item)
            entry = polling_entry(item)
            if self._dedupe.register(entry.message_id):
                await self._emit(entry)
        self._shared_runtime.mark_poll()

    async def _websocket_loop(self) -> None:
        attempt = 0
        while not self._stop_requested:
            try:
                self._refresh_settings()
                if not self._config.enable_websocket:
                    self._mark_websocket_idle()
                    await asyncio.sleep(10)
                    continue
                if not self._config.push_token:
                    self._mark_error("WXPUSHER_PUSH_TOKEN missing")
                    self._mark_websocket_idle()
                    await asyncio.sleep(10)
                    continue
                await self._consume_websocket()
                attempt = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                delay = RECONNECT_DELAYS[min(attempt, len(RECONNECT_DELAYS) - 1)]
                attempt += 1
                self._mark_reconnecting(f"WebSocket disconnected: {exc}; retry in {delay}s")
                await asyncio.sleep(delay)

    async def _consume_websocket(self) -> None:
        async with websockets.connect(self._client.websocket_url(), ping_interval=None) as ws:
            self._mark_connected()
            heartbeat = asyncio.create_task(self._heartbeat_loop(ws))
            try:
                async for raw in ws:
                    await self._handle_websocket_payload(raw)
            finally:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat

    async def _heartbeat_loop(self, ws) -> None:
        while True:
            await ws.send(json.dumps({"msgType": 101}))
            await asyncio.sleep(25)

    async def _handle_websocket_payload(self, raw: str) -> None:
        payload = json.loads(raw)
        msg_type = payload.get("msgType")
        if msg_type == 201:
            self._state.last_heartbeat = app_now()
            self._shared_runtime.mark_heartbeat()
            return
        if msg_type == 202:
            self._handle_init_payload(payload)
            return
        if msg_type == 20001:
            self._shared_runtime.save_message("websocket", payload)
            entry = websocket_entry(payload)
            if self._dedupe.register(entry.message_id):
                await self._emit(entry)

    def _handle_init_payload(self, payload: dict) -> None:
        token = payload.get("pushToken")
        if token and token != self._config.push_token:
            self._mark_error("WxPusher returned a new pushToken")
            return
        self._state.last_heartbeat = app_now()
        self._shared_runtime.mark_heartbeat()

    async def _emit(self, entry: LogEntry) -> None:
        self._state.last_heartbeat = app_now()
        self._shared_runtime.mark_heartbeat()
        if self._on_message:
            await self._on_message(entry)

    def _enabled_channels(self) -> list[str]:
        channels = []
        if self._config.enable_polling:
            channels.append("polling")
        if self._config.enable_websocket:
            channels.append("websocket")
        return channels

    def _mark_connected(self) -> None:
        self._state.status = ConnectionStatus.CONNECTED
        self._state.error_message = None
        self._state.last_heartbeat = app_now()
        self._sync_channels()
        self._shared_runtime.mark_heartbeat()

    def _mark_reconnecting(self, message: str) -> None:
        self._state.status = ConnectionStatus.RECONNECTING
        self._state.error_message = message
        self._sync_channels()
        self._shared_runtime.mark_error(message)

    def _mark_error(self, message: str) -> None:
        self._state.status = ConnectionStatus.ERROR
        self._state.error_message = message
        self._sync_channels()
        self._shared_runtime.mark_error(message)

    def _mark_websocket_idle(self) -> None:
        self._sync_channels()
        if not self._config.enable_polling:
            self._state.status = ConnectionStatus.DISCONNECTED
            self._state.error_message = None

    def _refresh_settings(self) -> None:
        self._shared_runtime.refresh()
        self._sync_channels()

    def _sync_channels(self) -> None:
        self._state.monitored_channels = self._enabled_channels()
