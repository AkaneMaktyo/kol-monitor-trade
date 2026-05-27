"""Signal replay and dashboard API routes."""

import asyncio
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.persistence.replay_store import ReplayStore
from app.persistence.signal_board_store import SignalBoardStore
from app.services.replay import ReplayActionService, ReplayQueryService
from app.services.dashboard.trading_board import TradingBoardService
from app.services.signal_chain import HistoricalSignalChain

router = APIRouter(prefix="/api/signals", tags=["signals"])


class ReplayActionPayload(BaseModel):
    action: str = Field(pattern="^(preview|persist|real_execute)$")
    log_ids: list[str] = Field(min_length=1, max_length=120)
    confirmation_text: str = ""


@router.get("/board")
async def signal_board(request: Request, limit: int = 6):
    service = TradingBoardService(
        request.app.state.config,
        SignalBoardStore(request.app.state.config.mysql),
    )
    return await asyncio.to_thread(service.load, limit)


@router.get("/gold-empire/replay")
async def replay_gold_empire(
    request: Request,
    limit: int = 120,
    persist: bool = False,
    ignore_stale: bool = False,
):
    chain = HistoricalSignalChain(
        request.app.state.log_store,
        request.app.state.config.wxpusher,
        request.app.state.trading_executor,
    )
    return await chain.replay_gold_empire(
        limit=limit,
        persist=persist,
        ignore_stale=ignore_stale,
    )


@router.get("/replay/gold-empire")
async def replay_gold_empire_page(
    request: Request,
    author: str = "",
    source_channel: str = "",
    candidate_status: str = "",
    execution_status: str = "",
    limit: int = 120,
):
    service = ReplayQueryService(
        request.app.state.config,
        ReplayStore(request.app.state.config.mysql),
        request.app.state.trading_executor,
    )
    return await service.load_gold_empire(
        author=author,
        source_channel=source_channel,
        candidate_status=candidate_status,
        execution_status=execution_status,
        limit=limit,
    )


@router.post("/replay/gold-empire/actions")
async def replay_gold_empire_actions(payload: ReplayActionPayload, request: Request):
    service = ReplayActionService(
        request.app.state.config,
        ReplayStore(request.app.state.config.mysql),
        request.app.state.trading_executor,
    )
    try:
        return await service.run_gold_empire(
            payload.action,
            payload.log_ids,
            payload.confirmation_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
