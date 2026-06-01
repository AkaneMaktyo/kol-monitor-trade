from app.config import AppConfig
from app.models import app_now
from app.persistence.wxpusher_shared import SharedWxPusherSettings, SharedWxPusherStore


class SharedWxPusherRuntime:
    def __init__(self, config: AppConfig):
        self._config = config
        self._store = SharedWxPusherStore(config.mysql, config.wxpusher.shared_database)

    def initialize(self) -> None:
        self._store.initialize()
        self._store.ensure_settings(self._defaults())
        self.refresh()

    def refresh(self) -> None:
        self._store.load_settings(self._defaults()).apply(self._config.wxpusher)

    def save_message(self, channel: str, item: dict) -> None:
        self._store.save_message(channel, item)

    def mark_heartbeat(self) -> None:
        self._store.update_runtime(heartbeat_at=app_now(), error="")

    def mark_poll(self) -> None:
        now = app_now()
        self._store.update_runtime(heartbeat_at=now, error="", poll_at=now)

    def mark_error(self, message: str) -> None:
        self._store.update_runtime(error=message)

    def _defaults(self) -> SharedWxPusherSettings:
        return SharedWxPusherSettings.from_config(self._config.wxpusher)
