"""Sanitized WxPusher article HTML extraction."""

from html import escape, unescape
from html.parser import HTMLParser


class ArticleHtmlParser(HTMLParser):
    _allowed = {
        "p", "div", "span", "strong", "b", "em", "i", "u", "br", "ul",
        "ol", "li", "a", "img", "h1", "h2", "h3", "h4", "blockquote",
        "pre", "code",
    }
    _void = {"br", "img"}
    _skip = {"script", "style", "svg", "iframe", "object"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._capture = False
        self._body = False
        self._depth = 0
        self._skip_depth = 0
        self._parts: list[str] = []
        self._open: list[str] = []

    @classmethod
    def parse(cls, html: str) -> str:
        parser = cls()
        parser.feed(html)
        return "".join(parser._parts).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if not self._capture and tag == "main" and "article-content" in attrs_dict.get("class", ""):
            self._capture = True
            self._depth = 1
            return
        if not self._capture:
            return
        self._depth += 1
        if self._skip_depth or tag in self._skip:
            self._skip_depth += 1
            return
        if self._body and tag in self._allowed:
            self._parts.append(self._tag(tag, attrs_dict))
            if tag not in self._void:
                self._open.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self._capture:
            return
        if self._skip_depth:
            self._skip_depth -= 1
        elif self._body and tag in self._allowed and tag not in self._void:
            self._close(tag)
        self._depth -= 1
        if self._depth <= 0:
            self._capture = False

    def handle_data(self, data: str) -> None:
        if not self._capture or self._skip_depth:
            return
        text = data.strip()
        if not self._body:
            self._body = text == "文本内容"
            return
        if text:
            self._parts.append(escape(data))

    def _close(self, tag: str) -> None:
        if self._open and self._open[-1] == tag:
            self._parts.append(f"</{tag}>")
            self._open.pop()

    def _tag(self, tag: str, attrs: dict[str, str | None]) -> str:
        if tag == "a":
            href = _safe_url(attrs.get("href") or "")
            return f'<a href="{escape(href)}" target="_blank" rel="noopener noreferrer">' if href else "<a>"
        if tag == "img":
            src = _safe_url(attrs.get("src") or attrs.get("data-src") or "")
            alt = escape(attrs.get("alt") or "消息图片")
            return f'<img src="{escape(src)}" alt="{alt}">' if src else ""
        return f"<{tag}>"


def _safe_url(url: str) -> str:
    value = unescape(url).strip()
    return value if value.startswith(("http://", "https://")) else ""
