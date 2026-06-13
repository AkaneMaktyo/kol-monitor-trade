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


@router.get("/current")
async def account_current(request: Request):
    return await request.app.state.account_live.snapshot()


@router.get("/history")
async def account_history(request: Request):
    service = AccountOverviewService(request.app.state.config, request.app.state.account_store)
    return await asyncio.to_thread(service.load_history)


@router.get("/history-detail")
async def account_history_detail(request: Request, symbol: str, hold_side: str, closed_at: int, open_price: float = 0, open_size: float = 0, close_price: float = 0, net_profit: float = 0):
    detail = await asyncio.to_thread(
        request.app.state.account_store.get_history_lifecycle,
        symbol=symbol, hold_side=hold_side, closed_at_ms=closed_at, open_price=open_price, open_size=open_size,
    )
    return {"ok": True, "title": f"{symbol} {_side_text(hold_side)}生命周期", "html": _history_html(symbol, hold_side, open_price, close_price, open_size, net_profit, detail)}


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
    summary = "".join(_summary_card(label, value, tone) for label, value, tone in [
        ("合约", symbol, ""), ("方向", _side_text(hold_side), ""), ("开仓均价", _num(open_price), ""),
        ("平仓均价", _num(close_price), ""), ("开仓数量", _num(open_size), ""), ("净盈亏", _signed(net_profit), _sign_class(net_profit)),
    ])
    note = f"本地按合约、方向和仓位规模匹配到 {detail['matched_size']} 条开仓记录，候选池共 {detail['pool_size']} 条。"
    return "".join([
        '<article class="message-html history-shell">',
        '<section class="history-hero"><div class="history-summary-grid">', summary, "</div>",
        f'<p class="history-note">{escape(note)}</p></section><section class="history-section"><h3>完整链路</h3>',
        _timeline_html(detail), "</section></article>",
    ])


def _timeline_html(detail: dict) -> str:
    rows = [_signal_event(row) for row in detail.get("signals", [])] + [_update_event(row) for row in detail.get("updates", [])]
    rows = sorted((row for row in rows if row["time"]), key=lambda row: row["time"])
    if not rows:
        return '<p class="history-empty">这条历史仓位还没找到可关联的本地消息链路。</p>'
    return '<ol class="history-timeline">' + "".join(_event_html(row) for row in rows) + "</ol>"


def _signal_event(row: dict) -> dict:
    parsed = row.get("parsed_json") or {}
    return {
        "kind": "signal", "label": "开仓信号", "status": _status_text(row.get("order_status") or row.get("intent_status")),
        "status_class": _status_class(row.get("order_status") or row.get("intent_status")), "time": row.get("signal_time") or row.get("message_time") or "",
        "chips": _shared_chips(row) + _trade_chips(row) + _risk_chips(parsed) + _optional_chip("交易所订单", row.get("exchange_order_id")),
        "body": _message_text(row), "log_id": row.get("source_log_id", ""), "has_log": bool(row.get("message_time")),
    }


def _update_event(row: dict) -> dict:
    chips = _shared_chips(row) + [_chip("动作", _action_text(row.get("action"))), _chip("状态", _status_text(row.get("status")), _status_class(row.get("status")))]
    if row.get("close_fraction"):
        chips.append(_chip("比例", f"{round(float(row['close_fraction']) * 100)}%"))
    return {
        "kind": "update", "label": "仓位更新", "status": _action_text(row.get("action")), "status_class": "is-update",
        "time": row.get("updated_at") or row.get("message_time") or "", "chips": chips,
        "body": _message_text(row), "log_id": row.get("source_log_id", ""), "has_log": bool(row.get("message_time")),
    }


def _event_html(row: dict) -> str:
    action = ""
    if row["log_id"] and row["has_log"]:
        action = f'<button class="message-link" type="button" data-log-id="{escape(row["log_id"])}">打开原消息</button>'
    body = ""
    if row["body"] and row["body"] != "--":
        body = f'<details class="history-evidence"><summary>查看原始内容</summary><pre class="message-content">{escape(row["body"])}</pre></details>'
    return "".join([
        f'<li class="history-event {row["kind"]}"><div class="history-event-head"><div><span class="history-kind">{escape(row["label"])}</span>',
        f'<strong class="history-status {row["status_class"]}">{escape(row["status"])}</strong></div><time>{escape(row["time"])}</time></div>',
        '<div class="history-chip-row">', "".join(row["chips"]), "</div>", body,
        f'<div class="history-actions">{action}</div></li>',
    ])


def _shared_chips(row: dict) -> list[str]:
    return [_chip("平台", row.get("platform")), _chip("作者", row.get("author")), _chip("通道", row.get("source_channel"))]


def _trade_chips(row: dict) -> list[str]:
    return [_chip("下单", _order_type_text(row.get("order_type"))), _chip("数量", _num(row.get("quantity"))), _chip("价格", _num(row.get("price")))]


def _risk_chips(parsed: dict) -> list[str]:
    chips = []
    if parsed.get("take_profits"):
        values = " / ".join(_num(item) for item in parsed.get("take_profits", []) if item is not None)
        if values:
            chips.append(_chip("止盈", values))
    if parsed.get("stop_loss"):
        chips.append(_chip("止损", _num(parsed.get("stop_loss"))))
    return chips


def _optional_chip(label: str, value) -> list[str]:
    return [_chip(label, value)] if value not in {None, ""} else []


def _chip(label: str, value, tone: str = "") -> str:
    text = "--" if value in {None, ""} else str(value)
    klass = f"history-chip {tone}".strip()
    return f'<span class="{klass}"><span>{escape(label)}</span><strong>{escape(text)}</strong></span>'


def _summary_card(label: str, value: str, tone: str) -> str:
    return f'<article class="history-summary-card {tone}"><span>{escape(label)}</span><strong>{escape(value)}</strong></article>'


def _message_text(row: dict) -> str:
    parsed = row.get("parsed_json") or {}
    return parsed.get("evidence_text") or row.get("content") or row.get("raw_text") or "--"


def _status_text(value: str) -> str:
    return {"ready": "就绪", "submitted": "已提交", "dry_run": "演练", "blocked": "已拦截", "needs_review": "待复核", "failed": "失败", "audit_only": "仅审计"}.get(str(value or "").lower(), value or "--")


def _status_class(value: str) -> str:
    return {"submitted": "is-good", "ready": "is-good", "dry_run": "is-warn", "needs_review": "is-warn", "blocked": "is-bad", "failed": "is-bad", "audit_only": "is-muted"}.get(str(value or "").lower(), "is-muted")


def _action_text(value: str) -> str:
    return {"close": "平仓", "add_layer": "补仓", "move_stop_to_breakeven": "保本移动", "risk_modifier": "风险调整", "take_partial_profit": "部分止盈", "take_profit_hit": "止盈触发"}.get(str(value or "").lower(), value or "--")


def _side_text(value: str) -> str:
    return {"long": "多仓", "short": "空仓"}.get(str(value or "").lower(), value or "--")


def _order_type_text(value: str) -> str:
    return {"market": "市价", "limit": "限价"}.get(str(value or "").lower(), value or "--")


def _sign_class(value) -> str:
    amount = float(value or 0)
    return "positive" if amount > 0 else "negative" if amount < 0 else ""


def _fallback_html(content: str) -> str:
    return f'<pre class="message-content">{escape(content)}</pre>'


def _num(value) -> str:
    try:
        return f"{float(value or 0):,.4f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "--"


def _signed(value) -> str:
    amount = float(value or 0)
    return f'{"+" if amount > 0 else ""}{_num(amount)}'
