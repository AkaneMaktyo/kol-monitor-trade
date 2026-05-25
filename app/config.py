"""环境配置加载。"""

import json
import os
from dataclasses import dataclass, field
from typing import List


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _env(key, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "on"}


def _env_list(key: str) -> List[str]:
    raw = _env(key)
    return [item.strip() for item in raw.split(",") if item.strip()] if raw else []


def _env_json(key: str) -> list:
    raw = _env(key)
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


@dataclass
class TelegramConfig:
    api_id: int = field(default_factory=lambda: _env_int("TELEGRAM_API_ID", 0))
    api_hash: str = field(default_factory=lambda: _env("TELEGRAM_API_HASH"))
    session_path: str = field(
        default_factory=lambda: _env("TELEGRAM_SESSION_PATH", "data/telegram_user")
    )
    proxy_url: str = field(default_factory=lambda: _env("TELEGRAM_PROXY_URL"))
    monitor_channels: List[str] = field(
        default_factory=lambda: _env_list("TELEGRAM_MONITOR_CHANNELS")
    )


@dataclass
class DiscordConfig:
    mode: str = field(default_factory=lambda: _env("DISCORD_MODE", "bot").lower())
    bot_token: str = field(default_factory=lambda: _env("DISCORD_BOT_TOKEN"))
    user_token: str = field(default_factory=lambda: _env("DISCORD_USER_TOKEN"))
    self_allow_send: bool = field(
        default_factory=lambda: _env_bool("DISCORD_SELF_ALLOW_SEND")
    )
    monitor_channels: List[str] = field(
        default_factory=lambda: _env_list("DISCORD_MONITOR_CHANNELS")
    )


@dataclass
class WxPusherConfig:
    device_token: str = field(default_factory=lambda: _env("WXPUSHER_DEVICE_TOKEN"))
    push_token: str = field(default_factory=lambda: _env("WXPUSHER_PUSH_TOKEN"))
    device_uuid: str = field(default_factory=lambda: _env("WXPUSHER_DEVICE_UUID"))
    platform: str = field(default_factory=lambda: _env("WXPUSHER_PLATFORM", "Chrome-Windows"))
    version: str = field(default_factory=lambda: _env("WXPUSHER_VERSION", "1.1.1"))
    poll_interval_seconds: int = field(
        default_factory=lambda: max(30, _env_int("WXPUSHER_POLL_INTERVAL_SECONDS", 60))
    )
    enable_polling: bool = field(
        default_factory=lambda: _env_bool("WXPUSHER_ENABLE_POLLING")
    )
    enable_websocket: bool = field(
        default_factory=lambda: _env_bool("WXPUSHER_ENABLE_WEBSOCKET")
    )


@dataclass
class MySQLConfig:
    host: str = field(default_factory=lambda: _env("MYSQL_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("MYSQL_PORT", 3306))
    user: str = field(default_factory=lambda: _env("MYSQL_USER", "root"))
    password: str = field(default_factory=lambda: _env("MYSQL_PASSWORD", ""))
    database: str = field(default_factory=lambda: _env("MYSQL_DATABASE", "kol_monitor_trade"))
    charset: str = field(default_factory=lambda: _env("MYSQL_CHARSET", "utf8mb4"))


@dataclass
class TradingConfig:
    enabled: bool = field(default_factory=lambda: _env_bool("TRADING_ENABLED"))
    execution_mode: str = field(default_factory=lambda: _env("TRADING_EXECUTION_MODE", "dry_run"))
    credential_database: str = field(
        default_factory=lambda: _env("TRADING_CREDENTIAL_DATABASE", "market_opinion_tracker")
    )
    proxy_url: str = field(default_factory=lambda: _env("TRADING_PROXY_URL"))
    account_equity_usdt: float = field(
        default_factory=lambda: _env_float("TRADING_ACCOUNT_EQUITY_USDT", 100.0)
    )
    max_stop_loss_percent: float = field(
        default_factory=lambda: _env_float("TRADING_MAX_STOP_LOSS_PERCENT", 5.0)
    )
    max_order_risk_usdt: float = field(
        default_factory=lambda: _env_float("TRADING_MAX_ORDER_RISK_USDT", 0.0)
    )
    max_signal_age_seconds: int = field(
        default_factory=lambda: _env_int("TRADING_MAX_SIGNAL_AGE_SECONDS", 900)
    )
    margin_mode: str = field(default_factory=lambda: _env("TRADING_MARGIN_MODE", "crossed"))
    product_type: str = field(default_factory=lambda: _env("TRADING_PRODUCT_TYPE", "USDT-FUTURES"))
    margin_coin: str = field(default_factory=lambda: _env("TRADING_MARGIN_COIN", "USDT"))


@dataclass
class PositionNotifyConfig:
    enabled: bool = field(default_factory=lambda: _env_bool("POSITION_NOTIFY_ENABLED"))
    channel: str = field(default_factory=lambda: _env("POSITION_NOTIFY_CHANNEL", "wxpusher"))
    interval_seconds: int = field(
        default_factory=lambda: max(15, _env_int("POSITION_NOTIFY_INTERVAL_SECONDS", 30))
    )
    wxpusher_spt: str = field(
        default_factory=lambda: _env("POSITION_NOTIFY_WXPUSHER_SPT")
    )
    wxpusher_app_token: str = field(
        default_factory=lambda: _env("POSITION_NOTIFY_WXPUSHER_APP_TOKEN")
    )
    wxpusher_uids: List[str] = field(
        default_factory=lambda: _env_list("POSITION_NOTIFY_WXPUSHER_UIDS")
    )
    wxpusher_topic_ids: List[str] = field(
        default_factory=lambda: _env_list("POSITION_NOTIFY_WXPUSHER_TOPIC_IDS")
    )


@dataclass
class ForwardRule:
    source: str
    source_channel: str
    target: str
    target_channel: str


@dataclass
class AppConfig:
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    wxpusher: WxPusherConfig = field(default_factory=WxPusherConfig)
    mysql: MySQLConfig = field(default_factory=MySQLConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    position_notify: PositionNotifyConfig = field(default_factory=PositionNotifyConfig)
    forward_rules: List[ForwardRule] = field(default_factory=list)
    host: str = field(default_factory=lambda: _env("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "info"))


def load_config() -> AppConfig:
    rules = []
    for item in _env_json("FORWARD_RULES"):
        try:
            rules.append(ForwardRule(
                source=str(item["source"]).lower(),
                source_channel=str(item["source_channel"]),
                target=str(item["target"]).lower(),
                target_channel=str(item["target_channel"]),
            ))
        except (KeyError, TypeError):
            continue
    return AppConfig(forward_rules=rules)
