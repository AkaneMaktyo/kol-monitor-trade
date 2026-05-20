"""统一消息接入服务。"""

import asyncio

from app.models import LogEntry, LogLevel, Platform, SystemState
from app.persistence.store import LogStore
from app.websocket_manager import ConnectionManager


class MessageService:
    def __init__(
        self,
        state: SystemState,
        store: LogStore,
        ws_manager: ConnectionManager,
    ):
        self._state = state
        self._store = store
        self._ws = ws_manager
        self._forwarder = None

    def set_forwarder(self, forwarder) -> None:
        self._forwarder = forwarder

    async def load_recent(self) -> None:
        self._state.log_entries = await asyncio.to_thread(self._store.hydrate_recent, 50)
        self._state.total_messages = await asyncio.to_thread(self._store.count)

    async def submit(self, entry: LogEntry, allow_forward: bool = True) -> LogEntry:
        self._remember(entry)
        await asyncio.to_thread(self._store.save, entry)
        await self._broadcast("log_entry", entry.to_dict())

        if allow_forward and self._forwarder and entry.platform in self._forwardable():
            results = await self._run_forwarder(entry)
            await self._record_forward_results(entry, results)

        self._state.forwarded_count = self._forwarded_count()
        return entry

    async def heartbeat(self) -> None:
        await self._broadcast(
            "heartbeat",
            self._state.to_dict(ws_clients=self._ws.active_count),
        )

    def _remember(self, entry: LogEntry) -> None:
        self._state.log_entries.append(entry)
        if len(self._state.log_entries) > 1000:
            self._state.log_entries = self._state.log_entries[-500:]
        self._state.total_messages += 1

    async def _run_forwarder(self, entry: LogEntry) -> list[dict]:
        if entry.platform == Platform.TELEGRAM:
            return await self._forwarder.handle_telegram_message(entry)
        if entry.platform == Platform.DISCORD:
            return await self._forwarder.handle_discord_entry(entry)
        return []

    async def _record_forward_results(self, entry: LogEntry, results: list[dict]) -> None:
        if not results:
            return
        entry.forwarded = any(item["success"] for item in results)
        await asyncio.to_thread(self._store.save, entry)
        for item in results:
            rule = item["rule"]
            level = LogLevel.FORWARD if item["success"] else LogLevel.ERROR
            content = f"转发到 {rule.target}:{rule.target_channel}"
            if item.get("error"):
                content += f" 失败: {item['error']}"
            event = LogEntry.create(
                level=level,
                platform=Platform.SYSTEM,
                source_channel=rule.source_channel,
                target_channel=rule.target_channel,
                content=content,
            )
            self._remember(event)
            await asyncio.to_thread(self._store.save, event)
            await self._broadcast("log_entry", event.to_dict())

    async def _broadcast(self, event_type: str, data: dict) -> None:
        await self._ws.broadcast({"type": event_type, "data": data})

    def _forwarded_count(self) -> int:
        return self._forwarder.forwarded_count if self._forwarder else 0

    @staticmethod
    def _forwardable() -> set[Platform]:
        return {Platform.TELEGRAM, Platform.DISCORD}
