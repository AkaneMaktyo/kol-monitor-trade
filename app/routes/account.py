"""Account overview API routes."""

import asyncio
from html import escape

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.account_actions import AccountActionService
from app.services.account_overview import AccountOverviewService
from app.services.wxpusher.detail import fetch_detail_html
from app.signals.normalizer import detail_url

router = APIRouter(prefix="/api/account", tags=["account"])


class ClosePositionPayload(BaseModel):
    symbol: str = Field(min_length=1, max_length=64)
    hold_side: str = Field(min_length=1, max_length=16)
    mode: str = Field(pattern="^(quantity|percent)$")
    quantity: float | None = None
    percent: float | None = None
    order_type: str = Field(default="market", pattern="^(market|limit)$")
    price: float | None = None


@router.get("/overview")
async def account_overview(request: Request):
    service = AccountOverviewService(
        request.app.state.config,
        request.app.state.account_store,
    )
    return await asyncio.to_thread(service.load)


@router.post("/close-position")
async def close_position(payload: ClosePositionPayload, request: Request):
    service = AccountActionService(request.app.state.config)
    try:
        return await asyncio.to_thread(service.close_position, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/message-detail")
async def account_message_detail(log_id: str, request: Request):
    entry = request.app.state.log_store.get_log(log_id)
    if not entry:
        raise HTTPException(status_code=404, detail="消息记录不存在")
    url = detail_url(entry)
    if not url:
        return {"ok": True, "html": _fallback_html(entry.get("content", ""))}
    try:
        html = await fetch_detail_html(url, request.app.state.config.wxpusher)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "html": html}


def _fallback_html(content: str) -> str:
    return f'<pre class="message-content">{escape(content)}</pre>'
