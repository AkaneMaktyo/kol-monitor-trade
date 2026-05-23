"""OpenAI 兼容大模型接口测试客户端。"""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LlmConfigError(RuntimeError):
    pass


def test_chat_completion(config: dict) -> dict:
    api_key = (config.get("api_key") or "").strip()
    base_url = (config.get("base_url") or "").strip().rstrip("/")
    model = (config.get("model") or "").strip()
    if not api_key:
        raise LlmConfigError("API Key 未配置")
    if not base_url.startswith("https://"):
        raise LlmConfigError("Base URL 必须使用 https")
    if not model:
        raise LlmConfigError("模型未配置")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "只回复 ok"}],
        "temperature": 0,
        "max_tokens": 16,
        "stream": False,
    }
    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LlmConfigError(f"模型接口返回 {exc.code}: {_short_error(body)}") from exc
    except URLError as exc:
        raise LlmConfigError(f"连接模型接口失败: {exc.reason}") from exc
    data = json.loads(raw)
    return {
        "model": data.get("model") or model,
        "content": _message_content(data),
        "usage": data.get("usage") or {},
    }


def _message_content(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()


def _short_error(body: str) -> str:
    try:
        data = json.loads(body)
        message = data.get("error", {}).get("message")
        return str(message or data)[:300]
    except json.JSONDecodeError:
        return body[:300]
