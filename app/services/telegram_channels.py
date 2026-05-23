"""Telegram 可见会话枚举。"""

import asyncio
import shutil
import tempfile
from pathlib import Path

from telethon import TelegramClient

from app.config import AppConfig
from app.telegram_monitor import _auth_marker, _parse_proxy, _session_file


async def list_telegram_channels(
    config: AppConfig,
    include_users: bool = False,
    limit: int = 300,
) -> list[dict]:
    if not config.telegram.api_id or not config.telegram.api_hash:
        raise ValueError("TELEGRAM_API_ID 或 TELEGRAM_API_HASH 未配置")
    if not _auth_marker(config).exists():
        raise ValueError("Telegram 会话未登录，请先运行 python -m app.telegram_monitor login")

    session_file = _session_file(config)
    if not session_file.exists():
        raise ValueError("Telegram 会话文件不存在")

    return await asyncio.to_thread(
        lambda: asyncio.run(_list_from_session_copy(config, session_file, include_users, limit))
    )


async def _list_from_session_copy(
    config: AppConfig,
    session_file: Path,
    include_users: bool,
    limit: int,
) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="kol_tg_") as temp_dir:
        session_base = Path(temp_dir) / "telegram_list"
        shutil.copy2(session_file, session_base.with_suffix(".session"))
        client = TelegramClient(
            str(session_base),
            config.telegram.api_id,
            config.telegram.api_hash,
            proxy=_parse_proxy(config.telegram.proxy_url),
        )
        await asyncio.wait_for(client.connect(), timeout=20)
        try:
            if not await client.is_user_authorized():
                raise ValueError("Telegram 会话未授权")
            rows = await _collect_dialogs(client, include_users, limit)
        finally:
            await client.disconnect()
    return sorted(rows, key=lambda item: (item["type"], item["title"].lower()))


async def _collect_dialogs(
    client: TelegramClient,
    include_users: bool,
    limit: int,
) -> list[dict]:
    rows = []
    async for dialog in client.iter_dialogs(limit=limit):
        item = _dialog_item(dialog)
        if include_users or item["id"].startswith("-"):
            rows.append(item)
    return rows


def _dialog_item(dialog) -> dict:
    entity = dialog.entity
    username = getattr(entity, "username", "") or ""
    return {
        "id": str(dialog.id),
        "title": dialog.name or getattr(entity, "title", "") or "",
        "username": f"@{username}" if username else "",
        "type": _dialog_type(entity),
        "unread": int(dialog.unread_count or 0),
    }


def _dialog_type(entity) -> str:
    raw_type = type(entity).__name__
    if raw_type == "Channel":
        return "channel" if getattr(entity, "broadcast", False) else "supergroup"
    if raw_type == "Chat":
        return "group"
    if raw_type == "User":
        return "user"
    return raw_type.lower()
