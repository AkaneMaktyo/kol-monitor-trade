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
    bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
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
class MySQLConfig:
    host: str = field(default_factory=lambda: _env("MYSQL_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("MYSQL_PORT", 3306))
    user: str = field(default_factory=lambda: _env("MYSQL_USER", "root"))
    password: str = field(default_factory=lambda: _env("MYSQL_PASSWORD", ""))
    database: str = field(default_factory=lambda: _env("MYSQL_DATABASE", "kol_monitor_trade"))
    charset: str = field(default_factory=lambda: _env("MYSQL_CHARSET", "utf8mb4"))


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
    mysql: MySQLConfig = field(default_factory=MySQLConfig)
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
