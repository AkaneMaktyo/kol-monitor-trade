import unittest

from app.services.youtube.client import YouTubeClient
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


if __name__ == "__main__":
    unittest.main()
