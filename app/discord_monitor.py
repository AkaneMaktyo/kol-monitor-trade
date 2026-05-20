"""Discord 消息监听器。"""

import asyncio
import importlib
import logging
from typing import Any, Callable, Optional

import discord

from app.config import AppConfig
from app.models import ConnectionStatus, LogEntry, LogLevel, Platform, PlatformConnectionState, utc_now

logger = logging.getLogger(__name__)
VALID_MODES = {"bot", "self"}


class DiscordMonitor:
    def __init__(self, config: AppConfig, state: PlatformConnectionState):
        self._config = config
        self._state = state
        self._client: Optional[Any] = None
        self._on_message: Optional[Callable] = None
        self._ready = asyncio.Event()

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_ready()

    async def start(self, on_message: Callable) -> None:
        mode = self._config.discord.mode
        if mode not in VALID_MODES:
            self._mark_error("DISCORD_MODE 仅支持 bot 或 self")
            return
        token = self._token_for_mode(mode)
        if not token:
            env_key = "DISCORD_USER_TOKEN" if mode == "self" else "DISCORD_BOT_TOKEN"
            self._mark_error(f"{env_key} 未配置")
            return

        self._on_message = on_message
        self._state.monitored_channels = list(self._config.discord.monitor_channels)
        self._ready.clear()

        try:
            self._client = self._create_client(mode)
            self._bind_events()
            asyncio.create_task(self._client.start(token))
            await asyncio.wait_for(self._ready.wait(), timeout=15)
        except asyncio.TimeoutError:
            self._state.status = ConnectionStatus.RECONNECTING
            self._state.error_message = "连接超时"
        except Exception as exc:
            self._mark_error(str(exc))
            logger.exception("Discord monitor failed")

    async def stop(self) -> None:
        if self._client and not self._client.is_closed():
            await self._client.close()
        self._client = None
        self._state.status = ConnectionStatus.DISCONNECTED

    async def send_message(self, channel_id: str, text: str) -> bool:
        if not self._client or not self._client.is_ready():
            return False
        if self._is_self_mode() and not self._config.discord.self_allow_send:
            logger.warning("self 模式未开启 DISCORD_SELF_ALLOW_SEND，跳过发送")
            return False
        channel = self._client.get_channel(int(channel_id))
        if channel is None:
            channel = await self._client.fetch_channel(int(channel_id))
        if not channel:
            return False
        await channel.send(text)
        return True

    def _bind_events(self) -> None:
        @self._client.event
        async def on_ready():
            self._state.status = ConnectionStatus.CONNECTED
            self._state.last_heartbeat = utc_now()
            self._state.error_message = None
            self._ready.set()
            logger.info(
                "Discord %s monitor started as %s",
                self._config.discord.mode,
                self._client.user,
            )

        @self._client.event
        async def on_message(message: Any):
            if message.author == self._client.user:
                return
            if not self._is_allowed(self._message_channel_ids(message)):
                return
            await self._emit_message(message)

        @self._client.event
        async def on_disconnect():
            self._state.status = ConnectionStatus.DISCONNECTED

        @self._client.event
        async def on_error(event, *args, **kwargs):
            self._mark_error(f"事件错误: {event}")

    async def _emit_message(self, message: Any) -> None:
        self._state.last_heartbeat = utc_now()
        author = message.author.name
        if getattr(message.author, "discriminator", "0") != "0":
            author = f"{message.author.name}#{message.author.discriminator}"
        entry = LogEntry.create(
            level=LogLevel.INFO,
            platform=Platform.DISCORD,
            source_channel=str(message.channel.id),
            content=(message.content or "[非文本消息]")[:1000],
            message_id=str(message.id),
            author=author,
        )
        if self._on_message:
            await self._on_message(entry)

    def list_channels(self) -> list[dict]:
        if not self._client or not self._client.is_ready():
            return []
        channels = []
        seen = set()
        for guild in getattr(self._client, "guilds", []):
            for channel in self._iter_guild_channels(guild):
                channel_id = str(getattr(channel, "id", ""))
                if not channel_id or channel_id in seen:
                    continue
                seen.add(channel_id)
                channels.append(self._channel_payload(guild, channel))
        return sorted(channels, key=lambda item: item["path"].lower())

    def _is_allowed(self, channel_ids: set[str]) -> bool:
        channels = self._config.discord.monitor_channels
        return not channels or bool(channel_ids.intersection(channels))

    @staticmethod
    def _message_channel_ids(message: Any) -> set[str]:
        channel = message.channel
        ids = {str(channel.id)}
        parent_id = getattr(channel, "parent_id", None)
        parent = getattr(channel, "parent", None)
        if parent_id:
            ids.add(str(parent_id))
        if parent and getattr(parent, "id", None):
            ids.add(str(parent.id))
        return ids

    @staticmethod
    def _iter_guild_channels(guild: Any) -> list[Any]:
        channels = []
        for attr in ("text_channels", "forum_channels", "threads"):
            channels.extend(getattr(guild, attr, []) or [])
        return channels

    @staticmethod
    def _channel_payload(guild: Any, channel: Any) -> dict:
        parent = getattr(channel, "category", None) or getattr(channel, "parent", None)
        parent_id = getattr(channel, "parent_id", None) or getattr(parent, "id", "")
        guild_name = getattr(guild, "name", "")
        parent_name = getattr(parent, "name", "")
        channel_name = getattr(channel, "name", str(getattr(channel, "id", "")))
        return {
            "guild_id": str(getattr(guild, "id", "")),
            "guild_name": guild_name,
            "channel_id": str(getattr(channel, "id", "")),
            "channel_name": channel_name,
            "channel_type": str(getattr(channel, "type", type(channel).__name__)),
            "parent_id": str(parent_id) if parent_id else "",
            "parent_name": parent_name,
            "path": " / ".join(filter(None, [guild_name, parent_name, channel_name])),
        }

    def _create_client(self, mode: str) -> Any:
        if mode == "bot":
            intents = discord.Intents.default()
            intents.message_content = True
            return discord.Client(intents=intents)
        try:
            selfcord = importlib.import_module("selfcord")
        except ImportError as exc:
            raise RuntimeError("self 模式需要安装 selfcord.py 依赖") from exc
        return selfcord.Client()

    def _token_for_mode(self, mode: str) -> str:
        if mode == "self":
            return self._config.discord.user_token
        return self._config.discord.bot_token

    def _is_self_mode(self) -> bool:
        return self._config.discord.mode == "self"

    def _mark_error(self, message: str) -> None:
        self._state.status = ConnectionStatus.ERROR
        self._state.error_message = message
