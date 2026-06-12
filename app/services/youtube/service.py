import os
from datetime import datetime
from pathlib import Path

from app.config import MySQLConfig
from app.persistence.youtube import YouTubeStore
from app.services.youtube.client import YouTubeClient
from app.services.youtube.downloader import YouTubeAudioDownloader
from app.services.youtube.oss import AliyunOssUploader
from app.services.youtube.transcriber import AudioTranscriber


class YouTubeService:
    def __init__(self, config: MySQLConfig):
        self._store = YouTubeStore(config)
        self._client = YouTubeClient()
        self._downloader = YouTubeAudioDownloader(Path("data") / "youtube_audio")
        self._uploader = AliyunOssUploader()
        self._transcriber = AudioTranscriber()
        self._max_videos = max(1, int(os.getenv("YOUTUBE_SYNC_MAX_VIDEOS", "1") or 1))
        self._ready = False

    def list_dashboard(self) -> list[dict]:
        self._ensure()
        channels = self._store.list_channels()
        for item in channels:
            item["videos"] = self._store.list_videos(item["id"])
        return channels

    def add_channel(self, source_url: str, name: str = "") -> dict:
        self._ensure()
        channel = self._client.resolve_channel(source_url)
        now = self._now()
        saved = self._store.save_channel(
            {
                **channel,
                "title": name.strip() or channel["title"],
                "updated_at": now,
                "last_checked_at": "",
                "last_video_published_at": "",
            }
        )
        return self.sync_channel(saved["id"])

    def sync_channel(self, channel_row_id: str) -> dict:
        self._ensure()
        channel = self._store.get_channel(channel_row_id)
        if not channel:
            raise ValueError("频道不存在")
        latest = channel["last_video_published_at"]
        saved = []
        for item in self._client.list_videos(channel["channel_id"], limit=self._max_videos):
            latest = max(latest, item["published_at"])
            saved.append(self._sync_video(channel, item))
        self._store.save_channel(
            {
                **channel,
                "updated_at": self._now(),
                "last_checked_at": self._now(),
                "last_video_published_at": latest,
            }
        )
        return {"channel": self._store.get_channel(channel["id"]), "videos": saved}

    def sync_all(self) -> list[dict]:
        self._ensure()
        return [self.sync_channel(item["id"]) for item in self._store.list_channels() if item["enabled"]]

    def delete_channel(self, channel_row_id: str) -> bool:
        self._ensure()
        return self._store.delete_channel(channel_row_id)

    def get_video(self, video_id: str) -> dict | None:
        self._ensure()
        return self._store.get_video(video_id)

    def ensure_audio(self, video_id: str) -> dict | None:
        self._ensure()
        video = self._store.get_video(video_id)
        if not video:
            return None
        path = self._audio_path(video.get("audio_path", ""))
        if path and path.exists():
            return video
        if not video.get("video_url"):
            return video
        audio = self._downloader.download(video["video_id"], video["video_url"])
        return self._store.save_video({**video, **audio, "updated_at": self._now()})

    def get_cloud_audio_link(self, video_id: str) -> str:
        self._ensure()
        video = self._store.get_video(video_id)
        if not video or video.get("transcript_source") != "aliyun_filetrans":
            return ""
        return self._uploader.sign_video_audio(video_id)

    def _sync_video(self, channel: dict, video: dict) -> dict:
        existing = self._store.get_video(video["video_id"])
        existing_path = self._audio_path(existing.get("audio_path", "")) if existing else None
        if existing and existing["transcript_status"] == "ready" and existing_path and existing_path.exists():
            return existing
        now = self._now()
        audio = self._downloader.download(video["video_id"], video["video_url"])
        try:
            transcript = self._transcriber.transcribe(audio["audio_path"])
        except ValueError as exc:
            transcript = {
                "transcript_status": "error",
                "transcript_language": "",
                "transcript_source": "",
                "transcript_text": "",
                "transcript_segments": [],
                "error_message": str(exc),
            }
        return self._store.save_video(
            {
                **video,
                **audio,
                **transcript,
                "channel_row_id": channel["id"],
                "channel_id": channel["channel_id"],
                "synced_at": now,
                "updated_at": now,
            }
        )

    def _ensure(self) -> None:
        if not self._ready:
            self._store.initialize()
            self._ready = True

    @staticmethod
    def _audio_path(raw_path: str) -> Path | None:
        return Path(raw_path.replace("\\", "/")) if raw_path else None

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
