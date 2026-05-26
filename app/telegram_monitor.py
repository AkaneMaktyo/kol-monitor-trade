"""Telegram 用户账号消息监听器。"""

import asyncio
import getpass
import logging
import sys
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

from app.config import AppConfig, load_config
from app.models import ConnectionStatus, LogEntry, LogLevel, Platform
from app.models import PlatformConnectionState, app_now

logger = logging.getLogger(__name__)


class TelegramMonitor:
    def __init__(self, config: AppConfig, state: PlatformConnectionState):
        self._config = config
        self._state = state
        self._client: Optional[TelegramClient] = None
        self._on_message: Optional[Callable] = None

    @property
    def is_connected(self) -> bool:
        return bool(self._client and self._client.is_connected())

    async def start(self, on_message: Callable) -> None:
        self._state.monitored_channels = list(self._config.telegram.monitor_channels)
        if not self._has_credentials():
            self._mark_error("TELEGRAM_API_ID 或 TELEGRAM_API_HASH 未配置")
            return
        if not _auth_marker(self._config).exists():
            self._mark_error("Telegram 会话未登录，请先运行 python -m app.telegram_monitor login")
            return

        self._on_message = on_message
        try:
            self._client = _build_client(self._config)
            await asyncio.wait_for(self._client.connect(), timeout=15)
            if not await self._client.is_user_authorized():
                await self._client.disconnect()
                self._client = None
                self._mark_error("Telegram 会话未登录，请先运行 python -m app.telegram_monitor login")
                return
            self._client.add_event_handler(self._handle_message, events.NewMessage)
            self._state.status = ConnectionStatus.CONNECTED
            self._state.last_heartbeat = app_now()
            self._state.error_message = None
            logger.info("Telegram user-client monitor started")
        except asyncio.TimeoutError:
            self._mark_error("Telegram 连接超时，请检查网络或稍后重试")
            logger.exception("Telegram monitor timeout")
        except Exception as exc:
            self._mark_error(str(exc))
            logger.exception("Telegram monitor failed")

    async def stop(self) -> None:
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                logger.exception("Telegram monitor stop failed")
            finally:
                self._client = None
        self._state.status = ConnectionStatus.DISCONNECTED

    async def send_message(self, channel_id: str, text: str) -> bool:
        if not self._client or not self._client.is_connected():
            return False
        await self._client.send_message(channel_id, text)
        return True

    async def _handle_message(self, event) -> None:
        chat_id = str(event.chat_id or "")
        if not await self._is_allowed(event, chat_id):
            return

        message = event.message
        text = message.message or "[非文本消息]"
        self._state.last_heartbeat = app_now()
        entry = LogEntry.create(
            level=LogLevel.INFO,
            platform=Platform.TELEGRAM,
            source_channel=chat_id,
            content=text[:1000],
            message_id=f"{chat_id}:{message.id}",
            author=await self._sender_name(event),
        )
        if self._on_message:
            await self._on_message(entry)

    async def _is_allowed(self, event, chat_id: str) -> bool:
        channels = self._config.telegram.monitor_channels
        normalized = {str(item).strip() for item in channels if str(item).strip()}
        if not normalized:
            return False
        if "*" in normalized:
            return True
        chat = await event.get_chat()
        username = getattr(chat, "username", "") or ""
        identifiers = {chat_id, username, f"@{username}" if username else ""}
        return bool(identifiers.intersection(normalized))

    async def _sender_name(self, event) -> str:
        sender = await event.get_sender()
        if not sender:
            return "unknown"
        username = getattr(sender, "username", "") or ""
        if username:
            return username
        title = getattr(sender, "title", "") or ""
        first = getattr(sender, "first_name", "") or ""
        last = getattr(sender, "last_name", "") or ""
        return title or " ".join(part for part in [first, last] if part) or "unknown"

    def _has_credentials(self) -> bool:
        return bool(self._config.telegram.api_id and self._config.telegram.api_hash)

    def _mark_error(self, message: str) -> None:
        self._state.status = ConnectionStatus.ERROR
        self._state.error_message = message


def _build_client(config: AppConfig) -> TelegramClient:
    session_path = Path(config.telegram.session_path)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    return TelegramClient(
        str(session_path),
        config.telegram.api_id,
        config.telegram.api_hash,
        proxy=_parse_proxy(config.telegram.proxy_url),
    )


def _parse_proxy(proxy_url: str) -> tuple | None:
    if not proxy_url:
        return None
    parsed = urlparse(proxy_url)
    if parsed.scheme not in {"socks5", "socks4", "http"}:
        raise ValueError("TELEGRAM_PROXY_URL 仅支持 socks5、socks4 或 http")
    if not parsed.hostname or not parsed.port:
        raise ValueError("TELEGRAM_PROXY_URL 格式应类似 socks5://127.0.0.1:7897")
    username = unquote(parsed.username) if parsed.username else None
    password = unquote(parsed.password) if parsed.password else None
    return parsed.scheme, parsed.hostname, parsed.port, True, username, password


def _session_file(config: AppConfig) -> Path:
    path = Path(config.telegram.session_path)
    return path if str(path).endswith(".session") else Path(f"{path}.session")


def _auth_marker(config: AppConfig) -> Path:
    return _session_file(config).with_suffix(".authorized")


async def login_from_env() -> None:
    load_dotenv()
    config = load_config()
    if not config.telegram.api_id or not config.telegram.api_hash:
        print("请先配置 TELEGRAM_API_ID 和 TELEGRAM_API_HASH")
        return

    client = _build_client(config)
    try:
        await asyncio.wait_for(client.connect(), timeout=15)
    except asyncio.TimeoutError:
        print("Telegram 连接超时，请检查网络或稍后重试")
        return
    if await client.is_user_authorized():
        _auth_marker(config).write_text("ok", encoding="utf-8")
        print("Telegram 用户会话已登录")
        await client.disconnect()
        return

    phone = input("请输入 Telegram 手机号（含国家区号）：").strip()
    await client.send_code_request(phone)
    code = input("请输入 Telegram 验证码：").strip()
    try:
        await client.sign_in(phone=phone, code=code)
    except SessionPasswordNeededError:
        password = getpass.getpass("请输入两步验证密码：")
        await client.sign_in(password=password)
    _auth_marker(config).write_text("ok", encoding="utf-8")
    print(f"登录完成，会话已保存到 {config.telegram.session_path}")
    await client.disconnect()


if __name__ == "__main__" and sys.argv[-1] == "login":
    asyncio.run(login_from_env())
