from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from app.services.youtube import YouTubeService

router = APIRouter(tags=["youtube"])


class ChannelPayload(BaseModel):
    source_url: str = Field(min_length=3, max_length=255)
    name: str = Field(default="", max_length=120)


def _service(request: Request) -> YouTubeService:
    service = getattr(request.app.state, "youtube_service", None)
    if service is None:
        service = YouTubeService(request.app.state.config.mysql)
        request.app.state.youtube_service = service
    return service


@router.get("/youtube", response_class=HTMLResponse)
async def youtube_page(request: Request):
    return request.app.state.templates.TemplateResponse(request, "youtube.html")


@router.get("/api/youtube/channels")
async def list_channels(request: Request):
    return {"channels": _service(request).list_dashboard()}


@router.post("/api/youtube/channels")
async def create_channel(payload: ChannelPayload, request: Request):
    try:
        result = _service(request).add_channel(payload.source_url, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.post("/api/youtube/channels/{channel_row_id}/sync")
async def sync_channel(channel_row_id: str, request: Request):
    try:
        result = _service(request).sync_channel(channel_row_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.post("/api/youtube/sync")
async def sync_all(request: Request):
    return {"ok": True, "results": _service(request).sync_all()}


@router.get("/api/youtube/videos/{video_id}")
async def get_video(video_id: str, request: Request):
    video = _service(request).get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")
    return {"ok": True, "video": video}


@router.get("/api/youtube/audio/{video_id}")
async def get_audio(video_id: str, request: Request):
    video = _service(request).ensure_audio(video_id)
    if not video or not video["audio_path"]:
        raise HTTPException(status_code=404, detail="音频不存在")
    path = Path(video["audio_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="音频文件不存在")
    return FileResponse(path, filename=path.name)


@router.delete("/api/youtube/channels/{channel_row_id}")
async def delete_channel(channel_row_id: str, request: Request):
    if not _service(request).delete_channel(channel_row_id):
        raise HTTPException(status_code=404, detail="频道不存在")
    return {"ok": True}
