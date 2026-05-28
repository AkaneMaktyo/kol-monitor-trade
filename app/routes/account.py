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
    service = AccountOverviewService(request.app.state.config, request.app.state.account_store)
    return await asyncio.to_thread(service.load)


@router.get("/history-detail")
async def account_history_detail(
    request: Request,
    symbol: str,
    hold_side: str,
    closed_at: int,
    open_price: float = 0,
    open_size: float = 0,
    close_price: float = 0,
    net_profit: float = 0,
):
    detail = await asyncio.to_thread(
        request.app.state.account_store.get_history_lifecycle,
        symbol=symbol,
        hold_side=hold_side,
        closed_at_ms=closed_at,
        open_price=open_price,
        open_size=open_size,
    )
    return {
        "ok": True,
        "title": f"{symbol} {_side_text(hold_side)}生命周期",
        "html": _history_html(symbol, hold_side, open_price, close_price, open_size, net_profit, detail),
    }


@router.post("/close-position")
async def close_position(payload: ClosePositionPayload, request: Request):
    service = AccountActionService(request.app.state.config)
    try:
        return await asyncio.to_thread(service.close_position, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc) or "平仓请求失败") from exc


@router.get("/message-detail")
async def account_message_detail(log_id: str, request: Request):
    entry = request.app.state.log_store.get_log(log_id)
    if not entry:
        raise HTTPException(status_code=404, detail="消息记录不存在")
    url = detail_url(entry)
    if not url:
        return {"ok": True, "title": "来源消息", "html": _fallback_html(entry.get("content", ""))}
    try:
        html = await fetch_detail_html(url, request.app.state.config.wxpusher)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "title": "来源消息", "html": html}


def _history_html(symbol: str, hold_side: str, open_price: float, close_price: float, open_size: float, net_profit: float, detail: dict) -> str:
    parts = [
        '<article class="message-html">',
        "<h3>仓位摘要</h3>",
        "<ul>",
        f"<li>合约: {escape(symbol)}</li>",
        f"<li>方向: {escape(_side_text(hold_side))}</li>",
        f"<li>开仓均价: {_num(open_price)}</li>",
        f"<li>平仓均价: {_num(close_price)}</li>",
        f"<li>开仓数量: {_num(open_size)}</li>",
        f"<li>净盈亏: {_signed(net_profit)}</li>",
        "</ul>",
        f"<p>本地按合约、方向和仓位规模匹配到 {detail['matched_size']} 条开仓记录，候选池共 {detail['pool_size']} 条。</p>",
        "<h3>完整链路</h3>",
        _timeline_html(detail),
        "</article>",
    ]
    return "".join(parts)


def _timeline_html(detail: dict) -> str:
    rows = [_signal_event(row) for row in detail.get("signals", [])]
    rows.extend(_update_event(row) for row in detail.get("updates", []))
    rows = sorted((row for row in rows if row["time"]), key=lambda row: row["time"])
    if not rows:
        return "<p>这条历史仓位还没找到可关联的本地消息链路。</p>"
    return "<ol>" + "".join(_event_html(row) for row in rows) + "</ol>"


def _signal_event(row: dict) -> dict:
    note = f"下单 {_order_type_text(row.get('order_type'))} / 数量 {_num(row.get('quantity'))} / 价格 {_num(row.get('price'))}"
    if row.get("exchange_order_id"):
        note += f" / 订单号 {row['exchange_order_id']}"
    return {
        "time": row.get("signal_time") or row.get("message_time") or "",
        "title": f"开仓信号 · {_status_text(row.get('order_status') or row.get('intent_status'))}",
        "meta": f"{_source_meta(row)} / {note}",
        "body": _message_text(row),
        "log_id": row.get("source_log_id", ""),
        "has_log": bool(row.get("message_time")),
    }


def _update_event(row: dict) -> dict:
    note = f"{_action_text(row.get('action'))} / {_status_text(row.get('status'))}"
    if row.get("close_fraction"):
        note += f" / 比例 {round(float(row['close_fraction']) * 100)}%"
    return {
        "time": row.get("updated_at") or row.get("message_time") or "",
        "title": f"仓位更新 · {_action_text(row.get('action'))}",
        "meta": f"{_source_meta(row)} / {note}",
        "body": _message_text(row),
        "log_id": row.get("source_log_id", ""),
        "has_log": bool(row.get("message_time")),
    }


def _event_html(row: dict) -> str:
    button = ""
    if row["log_id"] and row.get("has_log"):
        button = f'<p><button class="message-link" type="button" data-log-id="{escape(row["log_id"])}">打开原消息</button></p>'
    return (
        "<li><details open>"
        f"<summary>{escape(row['time'])} · {escape(row['title'])}</summary>"
        f"<p>{escape(row['meta'])}</p>"
        f"<pre class=\"message-content\">{escape(row['body'])}</pre>{button}"
        "</details></li>"
    )


def _message_text(row: dict) -> str:
    parsed = row.get("parsed_json") or {}
    return parsed.get("evidence_text") or row.get("content") or row.get("raw_text") or "--"


def _source_meta(row: dict) -> str:
    parts = [row.get("platform") or "--", row.get("author") or "--", row.get("source_channel") or "--"]
    return " / ".join(str(part) for part in parts)


def _side_text(value: str) -> str:
    return {"long": "多仓", "short": "空仓"}.get(str(value or "").lower(), value or "--")


def _status_text(value: str) -> str:
    return {
        "ready": "就绪", "submitted": "已提交", "dry_run": "演练",
        "blocked": "已拦截", "needs_review": "待复核", "failed": "失败",
        "audit_only": "仅审计",
    }.get(str(value or "").lower(), value or "--")


def _action_text(value: str) -> str:
    return {
        "close": "平仓", "add_layer": "补仓", "move_stop_to_breakeven": "保本移动",
        "risk_modifier": "风险调整", "take_partial_profit": "部分止盈",
        "take_profit_hit": "止盈触发",
    }.get(str(value or "").lower(), value or "--")


def _order_type_text(value: str) -> str:
    return {"market": "市价", "limit": "限价"}.get(str(value or "").lower(), value or "--")


def _fallback_html(content: str) -> str:
    return f'<pre class="message-content">{escape(content)}</pre>'


def _num(value) -> str:
    try:
        return f"{float(value or 0):,.4f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "--"


def _signed(value) -> str:
    amount = float(value or 0)
    prefix = "+" if amount > 0 else ""
    return f"{prefix}{_num(amount)}"
