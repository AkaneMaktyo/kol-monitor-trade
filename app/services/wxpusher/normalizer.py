"""WxPusher 消息标准化与去重。"""

from collections import deque

from app.models import LogEntry, LogLevel, Platform


class MessageDeduplicator:
    def __init__(self, limit: int = 2000):
        self._limit = limit
        self._seen: set[str] = set()
        self._order: deque[str] = deque()

    def register(self, message_id: str) -> bool:
        if not message_id or message_id in self._seen:
            return False
        self._seen.add(message_id)
        self._order.append(message_id)
        while len(self._order) > self._limit:
            self._seen.discard(self._order.popleft())
        return True


def polling_entry(item: dict) -> LogEntry:
    return _entry(
        source_channel="polling",
        message_id=_polling_id(item),
        author=str(item.get("name") or "WxPusher"),
        title=str(item.get("title") or ""),
        summary=str(item.get("summary") or ""),
        url=str(item.get("url") or ""),
        source_url=str(item.get("sourceUrl") or ""),
    )


def websocket_entry(item: dict) -> LogEntry:
    title = str(item.get("title") or "")
    return _entry(
        source_channel="websocket",
        message_id=_websocket_id(item),
        author=_source_from_title(title) or "WxPusher",
        title=title,
        summary=str(item.get("summary") or ""),
        url=str(item.get("url") or ""),
        source_url=str(item.get("sourceUrl") or ""),
    )


def polling_sort_key(item: dict) -> int:
    value = item.get("createTime") or item.get("messageId") or 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _entry(
    source_channel: str,
    message_id: str,
    author: str,
    title: str,
    summary: str,
    url: str,
    source_url: str,
) -> LogEntry:
    return LogEntry.create(
        level=LogLevel.INFO,
        platform=Platform.WXPUSHER,
        source_channel=source_channel,
        content=_content(title, summary, url, source_url),
        message_id=message_id,
        author=author,
    )


def _content(title: str, summary: str, url: str, source_url: str) -> str:
    parts = []
    if title and not _is_subscription_title(title):
        parts.append(title)
    if summary and summary != title:
        parts.append(summary)
    if source_url:
        parts.append(f"原文: {source_url}")
    if url:
        parts.append(f"详情: {url}")
    return "\n".join(parts).strip() or "[WxPusher 空消息]"


def _is_subscription_title(title: str) -> bool:
    return title.startswith("您订阅的【") and title.endswith("】有新的消息")


def _source_from_title(title: str) -> str:
    if not _is_subscription_title(title):
        return ""
    return title.removeprefix("您订阅的【").removesuffix("】有新的消息")


def _polling_id(item: dict) -> str:
    return _message_id(item, "polling", item.get("messageId") or item.get("id"))


def _websocket_id(item: dict) -> str:
    return _message_id(item, "websocket", item.get("qid") or item.get("messageId"))


def _message_id(item: dict, channel: str, fallback) -> str:
    raw = item.get("sourceUrl") or item.get("url")
    if raw:
        return f"wxpusher:{raw}"
    if fallback:
        return f"{channel}:{fallback}"
    return f"{channel}:{item.get('createTime', '')}:{item.get('summary', '')}"
