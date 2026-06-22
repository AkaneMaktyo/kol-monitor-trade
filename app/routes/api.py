"""REST API 路由。"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.models import LogEntry, LogLevel, Platform
from app.services.telegram_channels import list_telegram_channels
from app.services.wxpusher.detail import fetch_detail_text

router = APIRouter(prefix="/api", tags=["api"])
LLM_DISABLED_MESSAGE = "项目已暂时禁用大模型相关能力"


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


def _llm_disabled() -> None:
    raise HTTPException(status_code=403, detail=LLM_DISABLED_MESSAGE)


@router.get("/status")
async def get_status(request: Request):
    state = request.app.state.system_state
    return state.to_dict(ws_clients=request.app.state.ws_manager.active_count)


@router.get("/logs")
async def get_logs(request: Request, limit: int = 50, level: str = "", platform: str = ""):
    store = request.app.state.log_store
    entries = store.list_logs(limit=limit, level=level, platform=platform)
    return {"total": len(entries), "entries": entries}


@router.get("/logs/{log_id}")
async def get_log(log_id: str, request: Request):
    entry = request.app.state.log_store.get_log(log_id)
    if not entry:
        raise HTTPException(status_code=404, detail="消息记录不存在")
    return {"ok": True, "entry": entry}


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


@router.get("/telegram/channels")
async def list_telegram_visible_channels(
    request: Request,
    include_users: bool = False,
    limit: int = 300,
):
    try:
        channels = await list_telegram_channels(
            request.app.state.config,
            include_users=include_users,
            limit=limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"total": len(channels), "channels": channels}


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


@router.get("/signal-prompts")
async def list_signal_prompts():
    _llm_disabled()


@router.post("/signal-prompts")
async def create_signal_prompt():
    _llm_disabled()


@router.put("/signal-prompts/{profile_id}")
async def update_signal_prompt(profile_id: str):
    _llm_disabled()


@router.delete("/signal-prompts/{profile_id}")
async def delete_signal_prompt(profile_id: str):
    _llm_disabled()


@router.get("/llm-config")
async def get_llm_config():
    _llm_disabled()


@router.put("/llm-config")
async def save_llm_config():
    _llm_disabled()


@router.post("/llm-config/test")
async def test_llm_config():
    _llm_disabled()


@router.get("/health")
async def health_check():
    return {"status": "ok"}
