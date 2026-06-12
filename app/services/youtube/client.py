import re
import xml.etree.ElementTree as ET

import httpx


class YouTubeClient:
    def __init__(self):
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        )

    def resolve_channel(self, source: str) -> dict:
        source = source.strip()
        direct_id = self._direct_channel_id(source)
        url = source if source.startswith("http") else f"https://www.youtube.com/channel/{direct_id or source}"
        html = self._client.get(url).text
        channel_id = (
            direct_id
            or self._search(html, r'"channelId":"(UC[\w-]+)"')
            or self._search(html, r'"externalId":"(UC[\w-]+)"')
            or self._search(html, r'"browseId":"(UC[\w-]+)"')
            or self._search(html, r'<meta itemprop="channelId" content="(UC[\w-]+)"')
        )
        if not channel_id:
            raise ValueError("无法识别频道，建议直接粘贴频道链接或 UC 开头 ID")
        return {
            "channel_id": channel_id,
            "title": self._search(html, r'<meta property="og:title" content="([^"]+)"') or channel_id,
            "handle": self._search(html, r'"canonicalBaseUrl":"(/@[^"]+)"'),
            "source_url": source,
        }

    def list_videos(self, channel_id: str, limit: int = 3) -> list[dict]:
        xml_text = self._client.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}").text
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        rows = []
        for entry in root.findall("atom:entry", ns)[:limit]:
            video_id = entry.findtext("yt:videoId", default="", namespaces=ns)
            rows.append(
                {
                    "video_id": video_id,
                    "title": entry.findtext("atom:title", default="", namespaces=ns),
                    "video_url": f"https://www.youtube.com/watch?v={video_id}",
                    "published_at": entry.findtext("atom:published", default="", namespaces=ns),
                }
            )
        return rows

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _direct_channel_id(source: str) -> str:
        if source.startswith("UC"):
            return source
        match = re.search(r"/channel/(UC[\w-]+)", source)
        return match.group(1) if match else ""

    @staticmethod
    def _search(text: str, pattern: str) -> str:
        match = re.search(pattern, text)
        return match.group(1) if match else ""
