"""WxPusher 详情页正文提取。"""

import asyncio
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.config import WxPusherConfig


async def fetch_detail_text(url: str, config: WxPusherConfig) -> str:
    _validate_url(url)
    return await asyncio.to_thread(_fetch, url, config)


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "wxpusher.zjiecode.com":
        raise ValueError("仅支持 WxPusher 详情链接")
    if not parsed.path.startswith("/api/message/"):
        raise ValueError("详情链接格式不正确")


def _fetch(url: str, config: WxPusherConfig) -> str:
    request = Request(url, headers=_headers(config))
    with urlopen(request, timeout=20) as response:
        html = response.read().decode("utf-8", errors="replace")
    text = ArticleTextParser.parse(html)
    if not text:
        raise ValueError("详情页没有可提取正文")
    return text[:8000]


def _headers(config: WxPusherConfig) -> dict:
    return {
        "deviceToken": config.device_token,
        "version": config.version,
        "platform": config.platform,
        "User-Agent": "Mozilla/5.0",
    }


class ArticleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._capture = False
        self._skip = False
        self._depth = 0
        self._parts: list[str] = []
        self._link_stack: list[str] = []

    @classmethod
    def parse(cls, html: str) -> str:
        parser = cls()
        parser.feed(html)
        return _normalize("".join(parser._parts))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "main" and "article-content" in attrs_dict.get("class", ""):
            self._capture = True
            self._depth = 1
            return
        if not self._capture:
            return
        self._depth += 1
        if tag in {"script", "style", "svg"}:
            self._skip = True
        if tag in {"br", "p", "div", "li", "section"}:
            self._parts.append("\n")
        if tag == "a":
            self._link_stack.append(attrs_dict.get("href") or "")
        if tag == "img":
            image_url = self._image_url(attrs_dict)
            image_text = f"[图片: {image_url}]" if image_url else "[图片]"
            self._parts.append(f"\n{image_text}\n")

    def handle_endtag(self, tag: str) -> None:
        if not self._capture:
            return
        if tag in {"script", "style", "svg"}:
            self._skip = False
        if tag in {"p", "div", "li", "section", "main"}:
            self._parts.append("\n")
        if tag == "a" and self._link_stack:
            self._link_stack.pop()
        self._depth -= 1
        if self._depth <= 0:
            self._capture = False

    def handle_data(self, data: str) -> None:
        if self._capture and not self._skip:
            self._parts.append(data)

    def _image_url(self, attrs: dict[str, str | None]) -> str:
        candidates = [self._link_stack[-1] if self._link_stack else ""]
        candidates.extend([attrs.get("src") or "", attrs.get("data-src") or ""])
        for url in candidates:
            url = unescape(url).strip()
            if url.startswith(("http://", "https://")):
                return url
        return ""


def _normalize(text: str) -> str:
    lines = [unescape(line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line and not _is_noise_line(line))


def _is_noise_line(line: str) -> bool:
    if line in {"Discord -> WxPusher", "PREMIUM SIGNALS", "打开 Discord 原消息", "文本内容"}:
        return True
    if line.startswith("Crypto") and "CIA" in line:
        return True
    return bool(re.match(r"^\d{4}年\d{1,2}月\d{1,2}日 \d{1,2}:\d{2}:\d{2}$", line))
