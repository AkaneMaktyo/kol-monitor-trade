import os

from app.services.youtube.audio import AliyunAudioNormalizer
from app.services.youtube.filetrans import AliyunFileTransClient
from app.services.youtube.oss import AliyunOssUploader


class AudioTranscriber:
    def __init__(self):
        self._app_key = os.getenv("ALIYUN_NLS_APP_KEY", "").strip()
        self._normalizer = AliyunAudioNormalizer()
        self._uploader = AliyunOssUploader()
        self._client = AliyunFileTransClient()

    def transcribe(self, audio_path: str) -> dict:
        if not self._app_key:
            raise ValueError("缺少阿里云 AppKey，请设置 ALIYUN_NLS_APP_KEY")
        normalized_path = self._normalizer.normalize(audio_path)
        upload = self._uploader.upload(normalized_path)
        payload = self._client.transcribe(upload["file_link"])
        segments = self._paragraphs(self._sentences(payload))
        if not segments:
            raise ValueError(f"阿里云录音文件识别未返回有效句子: {payload}")
        return {
            "transcript_status": "ready",
            "transcript_language": "zh",
            "transcript_source": "aliyun_filetrans",
            "transcript_text": "\n\n".join(item["text"] for item in segments),
            "transcript_segments": segments,
            "error_message": "",
        }

    @staticmethod
    def _sentences(payload: dict) -> list[dict]:
        sentences = payload.get("Sentences") or payload.get("sentences") or []
        return sentences if isinstance(sentences, list) else []

    @staticmethod
    def _paragraphs(sentences: list[dict]) -> list[dict]:
        blocks, current = [], None
        for item in sentences:
            text = AudioTranscriber._value(item, "Text", "text")
            text = " ".join(str(text).split()).strip()
            if not text:
                continue
            start_ms = AudioTranscriber._int_value(item, "BeginTime", "begin_time")
            end_ms = AudioTranscriber._int_value(item, "EndTime", "end_time", default=start_ms)
            if current and (start_ms - current["end_ms"] < 2500) and len(current["text"]) < 140:
                current["end_ms"] = end_ms
                current["text"] = f"{current['text']} {text}".strip()
                continue
            current = {"start_ms": start_ms, "end_ms": end_ms, "text": text}
            blocks.append(current)
        return blocks

    @staticmethod
    def _value(item: dict, *keys: str):
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return value
        return ""

    @staticmethod
    def _int_value(item: dict, *keys: str, default: int = 0) -> int:
        value = AudioTranscriber._value(item, *keys)
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default
