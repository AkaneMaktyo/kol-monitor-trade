"""Telegram 消息监听器。"""

import logging
from typing import Callable, Optional

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from app.config import AppConfig
from app.models import ConnectionStatus, LogEntry, LogLevel, Platform, PlatformConnectionState, utc_now

logger = logging.getLogger(__name__)


class TelegramMonitor:
    def __init__(self, config: AppConfig, state: PlatformConnectionState):
        self._config = config
        self._state = state
        self._app: Optional[Application] = None
        self._on_message: Optional[Callable] = None

    @property
    def is_connected(self) -> bool:
        return self._app is not None and self._app.running

    async def start(self, on_message: Callable) -> None:
        if not self._config.telegram.bot_token:
            self._mark_error("TELEGRAM_BOT_TOKEN 未配置")
            return

        self._on_message = on_message
        self._state.monitored_channels = list(self._config.telegram.monitor_channels)
        try:
            self._app = Application.builder().token(self._config.telegram.bot_token).build()
            handler = MessageHandler(
                (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
                self._handle_message,
            )
            self._app.add_handler(handler)
            await self._app.initialize()
            await self._app.start()
            if self._app.updater:
                await self._app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            self._state.status = ConnectionStatus.CONNECTED
            self._state.last_heartbeat = utc_now()
            self._state.error_message = None
            logger.info("Telegram monitor started")
        except Exception as exc:
            self._mark_error(str(exc))
            logger.exception("Telegram monitor failed")

    async def stop(self) -> None:
        if self._app:
            try:
                if self._app.updater:
                    await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception:
                logger.exception("Telegram monitor stop failed")
            finally:
                self._app = None
        self._state.status = ConnectionStatus.DISCONNECTED

    async def send_message(self, channel_id: str, text: str) -> bool:
        if not self._app or not self._app.bot:
            return False
        await self._app.bot.send_message(chat_id=channel_id, text=text)
        return True

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        if not message:
            return

        chat_id = str(message.chat_id)
        if not self._is_allowed(chat_id):
            return

        text = message.text or message.caption or "[非文本消息]"
        author = "unknown"
        if message.from_user:
            author = message.from_user.username or message.from_user.full_name

        self._state.last_heartbeat = utc_now()
        entry = LogEntry.create(
            level=LogLevel.INFO,
            platform=Platform.TELEGRAM,
            source_channel=chat_id,
            content=text[:1000],
            message_id=str(message.message_id),
            author=author,
        )
        if self._on_message:
            await self._on_message(entry)

    def _is_allowed(self, chat_id: str) -> bool:
        channels = self._config.telegram.monitor_channels
        return not channels or chat_id in channels

    def _mark_error(self, message: str) -> None:
        self._state.status = ConnectionStatus.ERROR
        self._state.error_message = message
