"""按配置规则转发消息。"""

import logging
from typing import Optional, TYPE_CHECKING

from app.config import AppConfig, ForwardRule
from app.models import LogEntry, Platform

if TYPE_CHECKING:
    from app.discord_monitor import DiscordMonitor
    from app.telegram_monitor import TelegramMonitor

logger = logging.getLogger(__name__)


class MessageForwarder:
    def __init__(self, config: AppConfig):
        self._config = config
        self._telegram: Optional["TelegramMonitor"] = None
        self._discord: Optional["DiscordMonitor"] = None
        self._forwarded_count = 0

    def set_telegram(self, monitor: "TelegramMonitor") -> None:
        self._telegram = monitor

    def set_discord(self, monitor: "DiscordMonitor") -> None:
        self._discord = monitor

    @property
    def forwarded_count(self) -> int:
        return self._forwarded_count

    async def handle_telegram_message(self, entry: LogEntry) -> list[dict]:
        return await self._handle_entry(entry, "telegram")

    async def handle_discord_entry(self, entry: LogEntry) -> list[dict]:
        return await self._handle_entry(entry, "discord")

    async def handle_wxpusher_entry(self, entry: LogEntry) -> list[dict]:
        return await self._handle_entry(entry, "wxpusher")

    async def _handle_entry(self, entry: LogEntry, source: str) -> list[dict]:
        results = []
        for rule in self._matching_rules(entry, source):
            results.append(await self._execute(rule, entry))
        return results

    def _matching_rules(self, entry: LogEntry, source: str) -> list[ForwardRule]:
        return [
            rule for rule in self._config.forward_rules
            if rule.source == source and rule.source_channel == entry.source_channel
        ]

    async def _execute(self, rule: ForwardRule, entry: LogEntry) -> dict:
        text = self._format(entry, rule)
        if rule.target == "discord":
            success, error = await self._send_discord(rule.target_channel, text)
        elif rule.target == "telegram":
            success, error = await self._send_telegram(rule.target_channel, text)
        else:
            success, error = False, f"未知目标平台: {rule.target}"

        if success:
            self._forwarded_count += 1
        logger.info(
            "forward %s:%s -> %s:%s success=%s",
            rule.source, rule.source_channel, rule.target, rule.target_channel, success,
        )
        return {"rule": rule, "success": success, "error": error}

    async def _send_discord(self, channel_id: str, text: str) -> tuple[bool, str]:
        if not self._discord or not self._discord.is_connected:
            return False, "Discord 未连接"
        try:
            return await self._discord.send_message(channel_id, text), ""
        except Exception as exc:
            return False, str(exc)

    async def _send_telegram(self, channel_id: str, text: str) -> tuple[bool, str]:
        if not self._telegram or not self._telegram.is_connected:
            return False, "Telegram 未连接"
        try:
            return await self._telegram.send_message(channel_id, text), ""
        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _format(entry: LogEntry, rule: ForwardRule) -> str:
        labels = {
            Platform.TELEGRAM: "Telegram",
            Platform.DISCORD: "Discord",
            Platform.WXPUSHER: "WxPusher",
        }
        label = labels.get(entry.platform, "系统")
        header = f"[来自 {label}]"
        if entry.author:
            header += f" {entry.author}"
        header += f"\n源频道: {entry.source_channel}"
        return f"{header}\n\n{entry.content[:1800]}"
