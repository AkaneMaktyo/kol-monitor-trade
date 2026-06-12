import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.youtube.client import YouTubeClient
from app.services.youtube.service import YouTubeService
from app.services.youtube.transcriber import AudioTranscriber


class YouTubeClientTests(unittest.TestCase):
    def test_direct_channel_id_from_plain_id_and_url(self):
        self.assertEqual(YouTubeClient._direct_channel_id("UCabc123"), "UCabc123")
        self.assertEqual(YouTubeClient._direct_channel_id("https://www.youtube.com/channel/UCxyz987"), "UCxyz987")

    def test_search_returns_empty_string_when_not_found(self):
        self.assertEqual(YouTubeClient._search("hello", r"world"), "")


class AudioTranscriberTests(unittest.TestCase):
    def test_paragraphs_accept_filetrans_sentence_shape(self):
        segments = AudioTranscriber._paragraphs(
            [
                {"Text": "第一句", "BeginTime": 0, "EndTime": 1200},
                {"Text": "第二句", "BeginTime": 2000, "EndTime": 3200},
                {"Text": "第三段", "BeginTime": 7000, "EndTime": 8600},
            ]
        )
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["text"], "第一句 第二句")
        self.assertEqual(segments[0]["start_ms"], 0)
        self.assertEqual(segments[0]["end_ms"], 3200)
        self.assertEqual(segments[1]["text"], "第三段")


class YouTubeServiceTests(unittest.TestCase):
    def test_ensure_audio_redownloads_when_saved_file_missing(self):
        with TemporaryDirectory() as tmpdir:
            ready_audio = Path(tmpdir) / "fresh.m4a"
            ready_audio.write_bytes(b"x")
            service = YouTubeService.__new__(YouTubeService)
            service._ready = True
            service._store = _FakeStore(
                {
                    "video_id": "vid-1",
                    "video_url": "https://example.com/watch?v=1",
                    "audio_path": str(Path(tmpdir) / "missing.m4a"),
                    "audio_duration_ms": 0,
                }
            )
            service._downloader = _FakeDownloader(
                {"audio_path": str(ready_audio), "audio_duration_ms": 1234}
            )
            service._now = staticmethod(lambda: "2026-06-12 12:00:00")
            saved = service.ensure_audio("vid-1")
            self.assertEqual(saved["audio_path"], str(ready_audio))
            self.assertEqual(saved["audio_duration_ms"], 1234)
            self.assertEqual(service._store.saved["updated_at"], "2026-06-12 12:00:00")


class _FakeStore:
    def __init__(self, video: dict):
        self.video = dict(video)
        self.saved = None

    def get_video(self, _video_id: str):
        return dict(self.video)

    def save_video(self, payload: dict):
        self.saved = dict(payload)
        self.video = dict(payload)
        return dict(payload)


class _FakeDownloader:
    def __init__(self, result: dict):
        self.result = dict(result)

    def download(self, video_id: str, video_url: str):
        self.called_with = (video_id, video_url)
        return dict(self.result)


if __name__ == "__main__":
    unittest.main()
