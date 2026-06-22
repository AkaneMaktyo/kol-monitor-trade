import logging
import threading
from typing import Callable, TypeVar

from app.config import AppConfig
from app.models import app_now
from app.persistence.wxpusher_shared import SharedWxPusherSettings, SharedWxPusherStore

logger = logging.getLogger(__name__)
INIT_TIMEOUT_SECONDS = 8
REFRESH_TIMEOUT_SECONDS = 3
T = TypeVar("T")


class SharedWxPusherRuntime:
    def __init__(self, config: AppConfig):
        self._config = config
        self._store = SharedWxPusherStore(config.mysql, config.wxpusher.shared_database)
        self._init_attempted = False

    def initialize(self) -> None:
        if self._init_attempted:
            return
        self._init_attempted = True
        self._run_with_timeout("initialize", self._initialize_store, timeout=INIT_TIMEOUT_SECONDS)

    def refresh(self) -> None:
        settings = self._run_with_timeout(
            "refresh settings",
            lambda: self._store.load_settings(self._defaults()),
            timeout=REFRESH_TIMEOUT_SECONDS,
        )
        if settings:
            settings.apply(self._config.wxpusher)

    def save_message(self, channel: str, item: dict) -> None:
        self._launch_background("save message", lambda: self._store.save_message(channel, item))

    def mark_heartbeat(self) -> None:
        self._launch_background(
            "mark heartbeat",
            lambda: self._store.update_runtime(heartbeat_at=app_now(), error=""),
        )

    def mark_poll(self) -> None:
        now = app_now()
        self._launch_background(
            "mark poll",
            lambda: self._store.update_runtime(heartbeat_at=now, error="", poll_at=now),
        )

    def mark_error(self, message: str) -> None:
        self._launch_background("mark error", lambda: self._store.update_runtime(error=message))

    def _defaults(self) -> SharedWxPusherSettings:
        return SharedWxPusherSettings.from_config(self._config.wxpusher)

    def _initialize_store(self) -> None:
        self._store.initialize()
        self._store.ensure_settings(self._defaults())
        settings = self._store.load_settings(self._defaults())
        settings.apply(self._config.wxpusher)

    def _launch_background(self, label: str, action: Callable[[], None]) -> None:
        thread = threading.Thread(
            target=self._run_background,
            args=(label, action),
            name=f"wxpusher-{label.replace(' ', '-')}",
            daemon=True,
        )
        thread.start()

    def _run_background(self, label: str, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as exc:
            logger.warning("Shared WxPusher %s failed: %s", label, exc)

    def _run_with_timeout(
        self,
        label: str,
        action: Callable[[], T],
        *,
        timeout: int,
    ) -> T | None:
        result: dict[str, T | Exception | None] = {"value": None, "error": None}

        def runner() -> None:
            try:
                result["value"] = action()
            except Exception as exc:
                result["error"] = exc

        thread = threading.Thread(
            target=runner,
            name=f"wxpusher-{label.replace(' ', '-')}",
            daemon=True,
        )
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            logger.warning("Shared WxPusher %s timed out after %ss; continuing", label, timeout)
            return None
        if result["error"]:
            logger.warning("Shared WxPusher %s failed: %s", label, result["error"])
            return None
        return result["value"]  # type: ignore[return-value]
