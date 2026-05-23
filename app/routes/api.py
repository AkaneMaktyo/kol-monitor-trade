"""REST API 路由。"""

import asyncio
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.models import LogEntry, LogLevel, Platform
from app.services.llm_client import LlmConfigError, test_chat_completion
from app.services.telegram_channels import list_telegram_channels
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


class PromptProfilePayload(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    source_author: str = Field(default="", max_length=255)
    source_channel: str = Field(default="", max_length=255)
    prompt: str = Field(min_length=10, max_length=12000)
    enabled: bool = True


class LlmConfigPayload(BaseModel):
    provider: str = Field(default="deepseek", max_length=40)
    base_url: str = Field(default="https://api.deepseek.com", max_length=255)
    model: str = Field(default="deepseek-v4-flash", max_length=120)
    api_key: str = Field(default="", max_length=4000)
    enabled: bool = True


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
async def list_signal_prompts(request: Request):
    store = request.app.state.prompt_store
    return {"profiles": store.list_profiles()}


@router.post("/signal-prompts")
async def create_signal_prompt(payload: PromptProfilePayload, request: Request):
    store = request.app.state.prompt_store
    profile = store.save(payload.model_dump())
    return {"ok": True, "profile": profile}


@router.put("/signal-prompts/{profile_id}")
async def update_signal_prompt(
    profile_id: str,
    payload: PromptProfilePayload,
    request: Request,
):
    store = request.app.state.prompt_store
    if not store.get(profile_id):
        raise HTTPException(status_code=404, detail="提示词配置不存在")
    data = payload.model_dump()
    data["id"] = profile_id
    profile = store.save(data)
    return {"ok": True, "profile": profile}


@router.delete("/signal-prompts/{profile_id}")
async def delete_signal_prompt(profile_id: str, request: Request):
    store = request.app.state.prompt_store
    if not store.delete(profile_id):
        raise HTTPException(status_code=404, detail="提示词配置不存在")
    return {"ok": True}


@router.get("/llm-config")
async def get_llm_config(request: Request):
    store = request.app.state.llm_store
    return {"config": store.get()}


@router.put("/llm-config")
async def save_llm_config(payload: LlmConfigPayload, request: Request):
    store = request.app.state.llm_store
    config = store.save(payload.model_dump())
    return {"ok": True, "config": config}


@router.post("/llm-config/test")
async def test_llm_config(payload: LlmConfigPayload, request: Request):
    store = request.app.state.llm_store
    data = store.get(include_key=True)
    incoming = payload.model_dump()
    data.update({key: value for key, value in incoming.items() if value or key == "enabled"})
    try:
        result = await asyncio.to_thread(test_chat_completion, data)
    except LlmConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "result": result}


@router.get("/health")
async def health_check():
    return {"status": "ok"}
