"""Trading control routes."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services.dashboard.trading_controls import TradingControlsService

router = APIRouter(prefix="/api/trading-controls", tags=["trading-controls"])


class TradingControlsPayload(BaseModel):
    enabled: bool
    execution_mode: Literal["dry_run", "auto_demo"]


@router.get("")
async def get_trading_controls(request: Request):
    return {"controls": _service(request).snapshot()}


@router.put("")
async def save_trading_controls(
    payload: TradingControlsPayload,
    request: Request,
):
    try:
        controls = _service(request).update(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "controls": controls}


def _service(request: Request) -> TradingControlsService:
    existing = getattr(request.app.state, "trading_controls_service", None)
    if existing:
        return existing
    return TradingControlsService(request.app.state.config)
