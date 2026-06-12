from pathlib import Path

import av
from yt_dlp import YoutubeDL


class YouTubeAudioDownloader:
    def __init__(self, root: Path):
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def download(self, video_id: str, video_url: str) -> dict:
        existing = self._existing(video_id)
        if existing:
            return {"audio_path": str(existing), "audio_duration_ms": self._duration_ms(existing)}
        options = {
            "format": "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio[ext=mp3]/bestaudio",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "outtmpl": str(self._root / f"{video_id}.%(ext)s"),
        }
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(video_url, download=True)
        file_path = self._download_path(video_id, info)
        duration_ms = int((info.get("duration") or 0) * 1000) or self._duration_ms(file_path)
        return {"audio_path": str(file_path), "audio_duration_ms": duration_ms}

    def _existing(self, video_id: str) -> Path | None:
        matches = [path for path in self._root.glob(f"{video_id}.*") if ".aliyun" not in path.name]
        return matches[0] if matches else None

    def _download_path(self, video_id: str, info: dict) -> Path:
        requested = info.get("requested_downloads") or []
        if requested and requested[0].get("filepath"):
            return Path(requested[0]["filepath"])
        filename = info.get("_filename")
        if filename:
            return Path(filename)
        existing = self._existing(video_id)
        if existing:
            return existing
        raise ValueError("音频下载完成但没有找到文件")

    @staticmethod
    def _duration_ms(path: Path) -> int:
        container = av.open(str(path))
        try:
            return int((container.duration or 0) / 1000)
        finally:
            container.close()
