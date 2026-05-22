"""页面路由。"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return request.app.state.templates.TemplateResponse(
        request,
        "dashboard.html",
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    config = request.app.state.config
    return request.app.state.templates.TemplateResponse(
        request,
        "settings.html",
        context={
            "request": request,
            "telegram_api_id": bool(config.telegram.api_id),
            "telegram_api_hash": bool(config.telegram.api_hash),
            "telegram_session_path": config.telegram.session_path,
            "telegram_proxy_url": config.telegram.proxy_url,
            "discord_mode": config.discord.mode,
            "discord_token": bool(config.discord.bot_token),
            "discord_user_token": bool(config.discord.user_token),
            "discord_self_allow_send": config.discord.self_allow_send,
            "telegram_channels": config.telegram.monitor_channels,
            "discord_channels": config.discord.monitor_channels,
            "wxpusher_device_token": bool(config.wxpusher.device_token),
            "wxpusher_push_token": bool(config.wxpusher.push_token),
            "wxpusher_device_uuid": bool(config.wxpusher.device_uuid),
            "wxpusher_polling": config.wxpusher.enable_polling,
            "wxpusher_websocket": config.wxpusher.enable_websocket,
            "wxpusher_interval": config.wxpusher.poll_interval_seconds,
            "wxpusher_platform": config.wxpusher.platform,
            "wxpusher_version": config.wxpusher.version,
            "forward_rules": config.forward_rules,
            "mysql": config.mysql,
        },
    )
