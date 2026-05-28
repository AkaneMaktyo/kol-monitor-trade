"""Runtime trading controls for the dashboard."""

import os
from pathlib import Path

from dotenv import set_key

from app.config import AppConfig

MODES = {"dry_run", "auto_demo"}


class TradingControlsService:
    def __init__(self, config: AppConfig, env_path: Path | None = None):
        self._config = config
        self._env_path = env_path or Path(__file__).resolve().parents[3] / ".env"

    def snapshot(self) -> dict:
        trading = self._config.trading
        return {
            "enabled": trading.enabled,
            "execution_mode": trading.execution_mode,
            "auto_submit": bool(
                trading.enabled and trading.execution_mode == "auto_demo"
            ),
        }

    def update(self, *, enabled: bool, execution_mode: str) -> dict:
        mode = str(execution_mode or "").strip().lower()
        if mode not in MODES:
            raise ValueError("不支持的执行方式")
        trading = self._config.trading
        trading.enabled = bool(enabled)
        trading.execution_mode = mode
        self._persist("TRADING_ENABLED", "true" if trading.enabled else "false")
        self._persist("TRADING_EXECUTION_MODE", trading.execution_mode)
        os.environ["TRADING_ENABLED"] = "true" if trading.enabled else "false"
        os.environ["TRADING_EXECUTION_MODE"] = trading.execution_mode
        return self.snapshot()

    def _persist(self, key: str, value: str) -> None:
        self._env_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._env_path.exists():
            self._env_path.write_text("", encoding="utf-8")
        set_key(
            str(self._env_path),
            key,
            value,
            quote_mode="never",
            encoding="utf-8",
        )
