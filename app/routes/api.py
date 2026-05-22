"""REST API 路由。"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.models import LogEntry, LogLevel, Platform
from app.services.wxpusher.detail import fetch_detail_text

router = APIRouter(prefix="/api", tags=["api"])


class IngestRequest(BaseModel):
    platform: Platform = Field(default=Platform.SYSTEM)
    content: str = Field(min_length=1, max_length=4000)
    level: LogLevel = Field(default=LogLevel.INFO)
    source_channel: str = ""
    target_channel: str = ""
    message_id: str = ""
    author: str = ""
    forwarded: bool = False
    error_message: str = ""


@router.get("/status")
async def get_status(request: Request):
    state = request.app.state.system_state
    return state.to_dict(ws_clients=request.app.state.ws_manager.active_count)


@router.get("/logs")
async def get_logs(request: Request, limit: int = 50, level: str = "", platform: str = ""):
    store = request.app.state.log_store
    entries = store.list_logs(limit=limit, level=level, platform=platform)
    return {"total": len(entries), "entries": entries}


@router.get("/stats")
async def get_stats(request: Request):
    state = request.app.state.system_state
    store = request.app.state.log_store
    return {
        "uptime_seconds": state.uptime_seconds,
        "forwarded_count": state.forwarded_count,
        "telegram_status": state.telegram.status.value,
        "discord_status": state.discord.status.value,
        "wxpusher_status": state.wxpusher.status.value,
        "total_logs": store.count(),
        "ws_clients": request.app.state.ws_manager.active_count,
    }


@router.get("/discord/channels")
async def list_discord_channels(request: Request):
    monitor = getattr(request.app.state, "discord_monitor", None)
    connected = bool(monitor and monitor.is_connected)
    channels = monitor.list_channels() if connected else []
    return {
        "connected": connected,
        "mode": request.app.state.config.discord.mode,
        "total": len(channels),
        "channels": channels,
    }


@router.post("/ingest")
async def ingest_message(payload: IngestRequest, request: Request):
    service = request.app.state.message_service
    entry = LogEntry.create(**payload.model_dump())
    saved = await service.submit(entry, allow_forward=False)
    return {"ok": True, "entry": saved.to_dict()}


@router.get("/wxpusher/detail")
async def get_wxpusher_detail(url: str, request: Request):
    try:
        content = await fetch_detail_text(url, request.app.state.config.wxpusher)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "content": content}


@router.get("/health")
async def health_check():
    return {"status": "ok"}
