"""Signal replay API routes."""

from fastapi import APIRouter, Request

from app.services.signal_chain import HistoricalSignalChain

router = APIRouter(prefix="/api/signals", tags=["signals"])


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
