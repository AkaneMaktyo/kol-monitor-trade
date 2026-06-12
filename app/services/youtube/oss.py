import os
from pathlib import Path

import oss2


class AliyunOssUploader:
    def __init__(self):
        self._ak_id = os.getenv("ALIYUN_AK_ID", "").strip()
        self._ak_secret = os.getenv("ALIYUN_AK_SECRET", "").strip()
        self._endpoint = self._endpoint_value()
        self._bucket_name = os.getenv("ALIYUN_OSS_BUCKET", "").strip()
        self._prefix = os.getenv("ALIYUN_OSS_PREFIX", "youtube-audio").strip("/") or "youtube-audio"
        self._expire_seconds = max(600, int(os.getenv("ALIYUN_OSS_SIGN_EXPIRE_SECONDS", "86400") or 86400))

    def upload(self, audio_path: str) -> dict:
        if not self._ak_id or not self._ak_secret:
            raise ValueError("缺少阿里云凭证，请设置 ALIYUN_AK_ID 和 ALIYUN_AK_SECRET")
        if not self._bucket_name or not self._endpoint:
            raise ValueError("缺少 OSS 配置，请设置 ALIYUN_OSS_BUCKET 和 ALIYUN_OSS_ENDPOINT")
        path = Path(audio_path)
        if not path.exists():
            raise ValueError(f"音频文件不存在: {audio_path}")
        bucket = oss2.Bucket(oss2.Auth(self._ak_id, self._ak_secret), self._endpoint, self._bucket_name)
        object_key = self._object_key(path)
        bucket.put_object_from_file(object_key, str(path))
        return {"oss_key": object_key, "file_link": bucket.sign_url("GET", object_key, self._expire_seconds)}

    def _object_key(self, path: Path) -> str:
        stem = path.stem.replace(" ", "-")
        return f"{self._prefix}/{stem}{path.suffix.lower()}"

    @staticmethod
    def _endpoint_value() -> str:
        raw = os.getenv("ALIYUN_OSS_ENDPOINT", "").strip().rstrip("/")
        if not raw:
            return ""
        return raw if raw.startswith("http") else f"https://{raw}"
