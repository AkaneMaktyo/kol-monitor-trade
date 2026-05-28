import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import AppConfig
from app.routes import trading_controls
from app.services.dashboard.trading_controls import TradingControlsService


class TradingControlsServiceTests(unittest.TestCase):
    def test_update_writes_env_and_mutates_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            config = AppConfig()
            service = TradingControlsService(config, env_path)

            result = service.update(enabled=True, execution_mode="auto_demo")

            self.assertTrue(config.trading.enabled)
            self.assertEqual(config.trading.execution_mode, "auto_demo")
            self.assertTrue(result["auto_submit"])
            content = env_path.read_text(encoding="utf-8")
            self.assertIn("TRADING_ENABLED=true", content)
            self.assertIn("TRADING_EXECUTION_MODE=auto_demo", content)

    def test_invalid_mode_raises_error(self):
        service = TradingControlsService(AppConfig(), Path(tempfile.gettempdir()) / "x.env")
        with self.assertRaisesRegex(ValueError, "不支持的执行方式"):
            service.update(enabled=True, execution_mode="live")


class TradingControlsRouteTests(unittest.TestCase):
    def test_put_updates_running_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            config = AppConfig()
            app = FastAPI()
            app.state.config = config
            app.state.trading_controls_service = TradingControlsService(config, env_path)
            app.include_router(trading_controls.router)

            response = TestClient(app).put(
                "/api/trading-controls",
                json={"enabled": False, "execution_mode": "dry_run"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertFalse(config.trading.enabled)
            self.assertEqual(config.trading.execution_mode, "dry_run")
            self.assertEqual(response.json()["controls"]["execution_mode"], "dry_run")

    def test_get_returns_current_snapshot(self):
        app = FastAPI()
        config = AppConfig()
        config.trading.enabled = True
        config.trading.execution_mode = "auto_demo"
        app.state.config = config
        app.state.trading_controls_service = TradingControlsService(config)
        app.include_router(trading_controls.router)

        response = TestClient(app).get("/api/trading-controls")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["controls"]["auto_submit"])


if __name__ == "__main__":
    unittest.main()
