import json
import os
import time

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest


class AliyunFileTransClient:
    def __init__(self):
        self._app_key = os.getenv("ALIYUN_NLS_APP_KEY", "").strip()
        self._ak_id = os.getenv("ALIYUN_AK_ID", "").strip()
        self._ak_secret = os.getenv("ALIYUN_AK_SECRET", "").strip()
        self._region = os.getenv("ALIYUN_FILETRANS_REGION") or os.getenv("ALIYUN_NLS_REGION", "cn-shanghai")
        self._product = os.getenv("ALIYUN_FILETRANS_PRODUCT", "nls-filetrans").strip()
        self._domain = os.getenv("ALIYUN_FILETRANS_DOMAIN", f"filetrans.{self._region}.aliyuncs.com").strip()
        self._version = os.getenv("ALIYUN_FILETRANS_VERSION", "2018-08-17").strip()
        self._poll_interval = max(2, int(os.getenv("ALIYUN_FILETRANS_POLL_SECONDS", "5") or 5))
        self._poll_attempts = max(12, int(os.getenv("ALIYUN_FILETRANS_POLL_ATTEMPTS", "120") or 120))
        self._client = AcsClient(self._ak_id, self._ak_secret, self._region)

    def transcribe(self, file_link: str) -> dict:
        self._validate()
        task_id = self._submit(file_link)
        for _ in range(self._poll_attempts):
            payload = self._get_result(task_id)
            status = str(payload.get("StatusText", "")).upper()
            if status == "SUCCESS":
                return self._result_payload(payload)
            if status == "SUCCESS_WITH_NO_VALID_FRAGMENT":
                raise ValueError("阿里云录音文件识别完成，但没有返回有效语音片段")
            if status in {"RUNNING", "QUEUEING"}:
                time.sleep(self._poll_interval)
                continue
            raise ValueError(f"阿里云录音文件识别失败: {payload}")
        raise ValueError("阿里云录音文件识别超时，请稍后重试")

    def _submit(self, file_link: str) -> str:
        task = {
            "appkey": self._app_key,
            "file_link": file_link,
            "version": "4.0",
            "enable_words": False,
        }
        payload = self._request("SubmitTask", {"Task": json.dumps(task, ensure_ascii=False)})
        task_id = str(payload.get("TaskId", "")).strip()
        if str(payload.get("StatusText", "")).upper() != "SUCCESS" or not task_id:
            raise ValueError(self._submit_error(payload))
        return task_id

    def _get_result(self, task_id: str) -> dict:
        return self._request("GetTaskResult", {"TaskId": task_id}, method="GET", use_query=True)

    def _request(self, action: str, params: dict, method: str = "POST", use_query: bool = False) -> dict:
        request = CommonRequest()
        request.set_method(method)
        request.set_product(self._product)
        request.set_domain(self._domain)
        request.set_version(self._version)
        request.set_action_name(action)
        for key, value in params.items():
            if use_query:
                request.add_query_param(key, value)
            else:
                request.add_body_params(key, value)
        payload = json.loads(self._client.do_action_with_exception(request))
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _result_payload(payload: dict) -> dict:
        result = payload.get("Result", {})
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return {"raw": result}
        return result if isinstance(result, dict) else {}

    def _validate(self) -> None:
        if not self._app_key:
            raise ValueError("缺少阿里云 AppKey，请设置 ALIYUN_NLS_APP_KEY")
        if not self._ak_id or not self._ak_secret:
            raise ValueError("缺少阿里云凭证，请设置 ALIYUN_AK_ID 和 ALIYUN_AK_SECRET")

    @staticmethod
    def _submit_error(payload: dict) -> str:
        status = str(payload.get("StatusText", "")).upper()
        if status == "USER_BIZDURATION_QUOTA_EXCEED":
            return "阿里云录音文件识别额度不足，请检查试用额度、日累计时长或计费配置"
        return f"阿里云录音文件任务提交失败: {payload}"
