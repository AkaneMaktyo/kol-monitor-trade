"""应用数据模型。"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Platform(str, Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WXPUSHER = "wxpusher"
    SYSTEM = "system"


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class LogLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FORWARD = "forward"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class LogEntry:
    id: str
    timestamp: str
    level: LogLevel
    platform: Platform
    source_channel: str = ""
    target_channel: str = ""
    content: str = ""
    message_id: str = ""
    author: str = ""
    forwarded: bool = False
    error_message: str = ""

    @classmethod
    def create(cls, level: LogLevel, content: str, **kwargs) -> "LogEntry":
        value = f"{time.time_ns()}_{hash(content) & 0xFFFF:04x}"
        return cls(id=value, timestamp=utc_now(), level=level, content=content, **kwargs)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "level": self.level.value,
            "platform": self.platform.value,
            "source_channel": self.source_channel,
            "target_channel": self.target_channel,
            "content": self.content,
            "message_id": self.message_id,
            "author": self.author,
            "forwarded": self.forwarded,
            "error_message": self.error_message,
        }


@dataclass
class PlatformConnectionState:
    platform: Platform
    status: ConnectionStatus = ConnectionStatus.DISCONNECTED
    last_heartbeat: Optional[str] = None
    error_message: Optional[str] = None
    monitored_channels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "platform": self.platform.value,
            "status": self.status.value,
            "last_heartbeat": self.last_heartbeat,
            "error_message": self.error_message,
            "monitored_channels": self.monitored_channels,
        }


@dataclass
class SystemState:
    telegram: PlatformConnectionState = field(
        default_factory=lambda: PlatformConnectionState(platform=Platform.TELEGRAM)
    )
    discord: PlatformConnectionState = field(
        default_factory=lambda: PlatformConnectionState(platform=Platform.DISCORD)
    )
    wxpusher: PlatformConnectionState = field(
        default_factory=lambda: PlatformConnectionState(platform=Platform.WXPUSHER)
    )
    log_entries: list[LogEntry] = field(default_factory=list)
    uptime_seconds: int = 0
    forwarded_count: int = 0
    total_messages: int = 0

    def to_dict(self, ws_clients: int = 0) -> dict:
        return {
            "telegram": self.telegram.to_dict(),
            "discord": self.discord.to_dict(),
            "wxpusher": self.wxpusher.to_dict(),
            "log_entries": [entry.to_dict() for entry in self.log_entries[-50:]],
            "uptime_seconds": self.uptime_seconds,
            "forwarded_count": self.forwarded_count,
            "total_messages": self.total_messages,
            "ws_clients": ws_clients,
        }
