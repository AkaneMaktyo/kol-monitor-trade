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
            "telegram_token": bool(config.telegram.bot_token),
            "discord_mode": config.discord.mode,
            "discord_token": bool(config.discord.bot_token),
            "discord_user_token": bool(config.discord.user_token),
            "discord_self_allow_send": config.discord.self_allow_send,
            "telegram_channels": config.telegram.monitor_channels,
            "discord_channels": config.discord.monitor_channels,
            "forward_rules": config.forward_rules,
            "mysql": config.mysql,
        },
    )
