"""Replay item inspection helpers."""

from app.config import AppConfig
from app.exchanges.bitget import BitgetDemoExchange
from app.models import app_now
from app.services.wxpusher.detail import fetch_detail_text
from app.signals.normalizer import detail_url, normalize_entry
from app.signals.parser import parse_signal
from app.trading.risk import describe_risk_budget


def replay_key(row: dict) -> str:
    content = row.get("content", "")
    for label in ("鍘熸枃:", "璇︽儏:"):
        for line in content.splitlines():
            if line.startswith(label):
                return line.split(":", 1)[1].strip()
    return row.get("id", "")


def build_live_context(config: AppConfig) -> dict:
    credential = BitgetDemoExchange(config).credential_status()
    trading = config.trading
    live_mode = bool(trading.enabled and trading.execution_mode == "auto_demo" and credential["ok"])
    disabled_reason = ""
    if not trading.enabled:
        disabled_reason = "交易开关未开启"
    elif trading.execution_mode != "auto_demo":
        disabled_reason = f"当前执行模式为 {trading.execution_mode}"
    elif not credential["ok"]:
        disabled_reason = credential["error"] or "Bitget demo 凭证未就绪"
    return {
        "live_mode": live_mode,
        "execution_mode": trading.execution_mode,
        "credential_status": "ready" if credential["ok"] else "missing",
        "credential_message": credential["error"] or "Bitget demo 凭证已就绪",
        "risk_budget": describe_risk_budget(trading),
        "disabled_reason": disabled_reason,
    }


async def inspect_log(
    config: AppConfig,
    executor,
    row: dict,
    *,
    persist: bool = False,
    allow_submit: bool = False,
    current_time: bool = False,
    live_context: dict | None = None,
) -> dict:
    detail_text, detail_state = await _load_detail(row, config)
    message = normalize_entry(row, detail_text)
    candidate = parse_signal(message)
    candidate_data = candidate.to_dict()
    audit = _audit(row) if current_time else None
    message_time = audit["triggered_at"] if audit else row.get("timestamp", "")
    result = executor.handle_candidate(
        candidate,
        message_time,
        persist=persist,
        allow_submit=allow_submit,
        audit=audit,
    )
    risk = _risk(result.get("intent"))
    execution = _execution(result, candidate_data)
    live = live_context or build_live_context(config)
    return {
        "log_id": row.get("id", ""),
        "timestamp": row.get("timestamp", ""),
        "author": row.get("author", ""),
        "source_channel": row.get("source_channel", ""),
        "content_preview": _preview(message.main_text or row.get("content", "")),
        "raw_content": row.get("content", ""),
        "detail_text": detail_text,
        "detail_state": detail_state,
        "normalized_text": message.main_text,
        "candidate": candidate_data,
        "risk": risk,
        "execution": execution,
        "selectable_actions": _actions(candidate.to_dict(), risk, live),
    }


async def _load_detail(row: dict, config: AppConfig) -> tuple[str, dict]:
    url = detail_url(row)
    if not url or "..." not in row.get("content", ""):
        return "", {"status": "not_needed", "url": url, "message": ""}
    try:
        text = await fetch_detail_text(url, config.wxpusher)
        return text, {"status": "fetched", "url": url, "message": ""}
    except Exception as exc:
        return "", {"status": "failed", "url": url, "message": str(exc)}


def _audit(row: dict) -> dict:
    return {
        "origin": "replay_manual",
        "origin_log_id": row.get("id", ""),
        "triggered_at": app_now(),
    }


def _risk(intent: dict | None) -> dict:
    if not intent:
        return {"status": "not_applicable", "reasons": [], "entry_price": 0, "quantity": 0}
    return {
        "status": intent.get("status", ""),
        "reasons": intent.get("reasons", []),
        "entry_price": intent.get("entry_price", 0),
        "quantity": intent.get("quantity", 0),
        "quote_risk_usdt": intent.get("quote_risk_usdt", 0),
        "risk_percent": intent.get("risk_percent", 0),
        "account_equity_usdt": intent.get("account_equity_usdt", 0),
    }


def _execution(result: dict, candidate: dict) -> dict:
    update = result.get("update")
    order = result.get("order")
    intent = result.get("intent")
    status = candidate.get("status", "")
    kind = "candidate"
    if intent:
        status = intent.get("status", status)
        kind = "intent"
    if update:
        status = update.get("status", status)
        kind = "update"
    if order:
        status = order.get("status", status)
        kind = "order"
    return {
        "kind": kind,
        "status": status,
        "signal_id": result.get("signal_id", ""),
        "intent_id": result.get("intent_id", ""),
        "update_id": result.get("update_id", ""),
        "intent": intent,
        "update": update,
        "order": order,
    }


def _actions(candidate: dict, risk: dict, live: dict) -> dict:
    real_ready = (
        candidate.get("category") == "new_signal"
        and candidate.get("status") == "parsed"
        and risk.get("status") == "ready"
    )
    reason = ""
    if candidate.get("category") != "new_signal":
        reason = "只有新开仓信号支持真实执行"
    elif candidate.get("status") != "parsed":
        reason = "信号尚未达到可执行解析状态"
    elif risk.get("status") != "ready":
        reason = ",".join(risk.get("reasons") or ["风险评估未通过"])
    elif not live.get("live_mode"):
        reason = live.get("disabled_reason", "")
    return {
        "preview": True,
        "persist": True,
        "real_execute": real_ready and live.get("live_mode", False),
        "real_execute_disabled_reason": "" if real_ready and live.get("live_mode") else reason,
        "batch_selectable": real_ready,
    }


def _preview(text: str) -> str:
    return " ".join(str(text or "").split())[:180]
