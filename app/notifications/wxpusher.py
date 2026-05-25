"""WxPusher notification sender."""

from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.config import PositionNotifyConfig

SEND_URL = "https://wxpusher.zjiecode.com/api/send/message"


@dataclass
class NotifyResult:
    ok: bool
    error: str = ""


class WxPusherNotifier:
    def __init__(self, config: PositionNotifyConfig):
        self._config = config

    @property
    def ready(self) -> bool:
        if self._config.wxpusher_spt:
            return True
        return bool(
            self._config.wxpusher_app_token
            and (self._config.wxpusher_uids or self._config.wxpusher_topic_ids)
        )

    async def send(self, title: str, content: str) -> NotifyResult:
        if not self.ready:
            return NotifyResult(False, "WxPusher 推送凭证未配置")
        try:
            if self._config.wxpusher_spt:
                return await self._send_spt(content)
            return await self._send_app(title, content)
        except httpx.HTTPError as exc:
            return NotifyResult(False, str(exc))

    async def _send_spt(self, content: str) -> NotifyResult:
        url = f"{SEND_URL}/{self._config.wxpusher_spt}/{quote(content, safe='')}"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
        return _result(response)

    async def _send_app(self, title: str, content: str) -> NotifyResult:
        payload = {
            "appToken": self._config.wxpusher_app_token,
            "summary": title[:100],
            "content": content,
            "contentType": 1,
            "uids": self._config.wxpusher_uids,
            "topicIds": _topic_ids(self._config.wxpusher_topic_ids),
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(SEND_URL, json=payload)
        return _result(response)


def _topic_ids(values: list[str]) -> list[int]:
    ids = []
    for value in values:
        try:
            ids.append(int(value))
        except ValueError:
            continue
    return ids


def _result(response: httpx.Response) -> NotifyResult:
    if not response.is_success:
        return NotifyResult(False, f"HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError:
        return NotifyResult(True, "")
    record_error = _record_error(data.get("data"))
    if record_error:
        return NotifyResult(False, record_error)
    code = str(data.get("code", ""))
    if data.get("success") is True or code in {"0", "200", "1000"}:
        return NotifyResult(True, "")
    return NotifyResult(False, str(data.get("msg") or data)[:300])


def _record_error(records) -> str:
    if not isinstance(records, list):
        return ""
    failures = []
    for item in records:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", ""))
        delivered = bool(item.get("sendRecordId") or item.get("messageId"))
        if code in {"0", "200", "1000"} or (not code and delivered):
            continue
        failures.append(str(item.get("status") or item)[:200])
    return "；".join(failures[:3])
