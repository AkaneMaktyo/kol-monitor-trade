"""Live signal processing from incoming log entries."""

from app.models import LogEntry, Platform
from app.services.wxpusher.detail import fetch_detail_text
from app.signals.normalizer import detail_url, is_gold_empire, normalize_entry
from app.signals.parser import parse_signal


class LiveSignalProcessor:
    def __init__(self, config, executor):
        self._config = config
        self._executor = executor

    async def handle(self, entry: LogEntry) -> dict | None:
        if entry.platform != Platform.WXPUSHER:
            return None
        data = entry.to_dict()
        if not is_gold_empire(data):
            return None
        detail = await self._detail(data)
        message = normalize_entry(data, detail)
        candidate = parse_signal(message)
        return self._executor.handle_candidate(
            candidate,
            entry.timestamp,
            persist=True,
        )

    async def _detail(self, data: dict) -> str:
        url = detail_url(data)
        if not url or "..." not in data.get("content", ""):
            return ""
        try:
            return await fetch_detail_text(url, self._config.wxpusher)
        except Exception:
            return ""
