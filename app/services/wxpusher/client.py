"""WxPusher 内部接口客户端。"""

import asyncio
import json
from urllib.parse import urlencode
from urllib.request import Request

from app.config import WxPusherConfig
from app.services.wxpusher.http import open_direct

LIST_URL = "https://wxpusher.zjiecode.com/api/need-login/device/message/list-v2"
MAX_MESSAGE_ID = "9223372036854775807"


class WxPusherLoginRequired(RuntimeError):
    pass


class WxPusherApiError(RuntimeError):
    pass


class WxPusherClient:
    def __init__(self, config: WxPusherConfig):
        self._config = config

    async def fetch_latest(self) -> list[dict]:
        return await asyncio.to_thread(self._fetch_latest)

    def websocket_url(self) -> str:
        query = urlencode({
            "version": self._config.version,
            "platform": self._config.platform,
            "pushToken": self._config.push_token,
        })
        return f"wss://wxpusher.zjiecode.com/ws?{query}"

    def _fetch_latest(self) -> list[dict]:
        query = urlencode({"messageId": MAX_MESSAGE_ID, "scene": "1", "key": ""})
        request = Request(
            f"{LIST_URL}?{query}",
            headers=self._headers(),
            method="GET",
        )
        with open_direct(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return self._extract_messages(payload)

    def _headers(self) -> dict:
        return {
            "deviceToken": self._config.device_token,
            "version": self._config.version,
            "platform": self._config.platform,
            "Content-Type": "application/json;charset=UTF-8",
        }

    def _extract_messages(self, payload: dict) -> list[dict]:
        code = payload.get("code")
        if code == 1002:
            raise WxPusherLoginRequired("WxPusher 登录态失效，请重新获取 token")
        if payload.get("success") is False and code not in (None, 1000):
            raise WxPusherApiError(str(payload.get("msg") or payload))
        data = payload.get("data", payload)
        items = self._find_list(data)
        if items is None:
            raise WxPusherApiError("WxPusher 返回结构无法识别")
        return [item for item in items if isinstance(item, dict)]

    def _find_list(self, data) -> list | None:
        if isinstance(data, list):
            return data
        if not isinstance(data, dict):
            return None
        for key in ("list", "records", "items", "messages", "rows"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        for value in data.values():
            nested = self._find_list(value)
            if nested is not None:
                return nested
        return None
