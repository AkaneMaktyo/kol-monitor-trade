"""Rule-based parser for high-confidence trading signals."""

import re

from app.signals.models import NormalizedMessage, SignalCandidate

UPDATE_RULES = [
    ("close", r"\b(trade close|close all|close now|close full|full close|close at breakeven)\b|平仓|全平|清仓|离场|出场|无盈无亏|不赚不亏"),
    ("take_partial_profit", r"\b(booked half|close first|partial|half profits?)\b|部分止盈|止盈一半|减仓|平一半|先出一半|锁定一半|已锁定一半"),
    ("move_stop_to_breakeven", r"\b(set\s*b\.?e\.?|breakeven|break even|sl move entry|move sl to entry)\b|保本|平保|盈亏平衡|止损.*(入场|成本)|移动止损"),
    ("take_profit_hit", r"\b(tp hit|target hit|target successfully hit|take profit hit)\b|止盈了|已止盈|成功止盈|达到止盈|目标达成"),
    ("hold", r"\b(hold last|keep holding|let it run)\b|继续持有|持有剩余|留尾仓|拿住"),
    ("risk_modifier", r"\b(risk half|half of normal risk)\b|半仓|小仓|减半风险|降低风险"),
    ("add_layer", r"\b(more buy|more sell|second entry|enter again|can enter)\b|加仓|补仓|再进|重新进|可以入场"),
]

SYMBOL_MAP = {
    "GOLD": ("XAUUSD", "XAUUSDT"),
    "XAU": ("XAUUSD", "XAUUSDT"),
    "XAUUSD": ("XAUUSD", "XAUUSDT"),
}


def parse_signal(message: NormalizedMessage) -> SignalCandidate:
    text = message.main_text
    body = _action_body(text)
    actions = _update_actions(body)
    if actions:
        return SignalCandidate(
            source_log_id=message.log_id,
            category="position_update",
            raw_text=message.raw_text,
            evidence_text=_evidence(text),
            source_url=message.source_url,
            reply_url=message.reply_url,
            action=actions[0],
            actions=actions,
            action_text=_evidence(body),
            close_fraction=_close_fraction(actions),
            confidence=0.86,
            status="parsed",
        )
    if _has_reply_quote(text):
        return _simple(message, "commentary", 0.35)
    if _media_only(text):
        return _simple(message, "media_or_link", 0.35)
    candidate = _parse_english_signal(message)
    if candidate:
        return candidate
    if _mentions_trade_intent(text):
        return _simple(message, "new_signal", 0.45, ["entry", "stop_loss", "take_profit"])
    return _simple(message, "commentary", 0.2)


def _parse_english_signal(message: NormalizedMessage) -> SignalCandidate | None:
    flat = _flat(message.main_text)
    if not _looks_like_new_signal(flat):
        return None
    symbol_raw = _symbol(flat)
    side = _side(flat)
    if not symbol_raw or not side:
        return None
    symbol, bitget_symbol = _map_symbol(symbol_raw)
    entries = _entry_numbers(flat)
    take_profits = _numbers_after("TP", flat)
    stop_loss = _first_after("SL", flat)
    missing = []
    if not entries:
        missing.append("entry")
    if not take_profits:
        missing.append("take_profit")
    if stop_loss is None:
        missing.append("stop_loss")
    confidence = 0.94 if not missing else 0.68
    return SignalCandidate(
        source_log_id=message.log_id,
        category="new_signal",
        raw_text=message.raw_text,
        evidence_text=_evidence(message.main_text),
        source_url=message.source_url,
        reply_url=message.reply_url,
        symbol=symbol,
        bitget_symbol=bitget_symbol,
        side=side,
        entry_numbers=entries,
        take_profits=take_profits,
        stop_loss=stop_loss,
        confidence=confidence,
        missing_fields=missing,
        status="parsed" if not missing else "needs_review",
    )


def _looks_like_new_signal(text: str) -> bool:
    has_side = re.search(r"\b(BUY|SELL|SELLING|BUYING)\b", text, flags=re.I)
    has_symbol = re.search(r"\b(GOLD|XAUUSD|XAU)\b", text, flags=re.I)
    return bool(has_side and has_symbol)


def _symbol(text: str) -> str:
    match = re.search(r"\$?(GOLD|XAUUSD|XAU)\b", text, flags=re.I)
    return match.group(1).upper() if match else ""


def _side(text: str) -> str:
    if re.search(r"\b(BUY|BUYING)\b", text, flags=re.I):
        return "long"
    if re.search(r"\b(SELL|SELLING)\b", text, flags=re.I):
        return "short"
    return ""


def _entry_numbers(text: str) -> list[float]:
    values = []
    values.extend(_numbers_after("@", text))
    values.extend(_numbers_after("ENTRY", text))
    return _unique(values[:3])


def _numbers_after(label: str, text: str) -> list[float]:
    escaped = re.escape(label)
    pattern = rf"{escaped}\s*:?\s*([0-9]+(?:\.[0-9]+)?)"
    return [float(item) for item in re.findall(pattern, text, flags=re.I)]


def _first_after(label: str, text: str) -> float | None:
    values = _numbers_after(label, text)
    return values[0] if values else None


def _update_actions(text: str) -> list[str]:
    return [action for action, pattern in UPDATE_RULES if re.search(pattern, text, flags=re.I)]


def _action_body(text: str) -> str:
    clean = re.sub(r"(回复|鍥炲|Reply)\s*:\s*\[[^\]]+\]\([^)]+\)", " ", text, flags=re.I)
    clean = re.sub(r"(回复|鍥炲|Reply)\s*:\s*https?://\S+", " ", clean, flags=re.I)
    clean = re.sub(r"\[[^\]]+\]\(https://[^)]+\)", " ", clean)
    return _flat(clean)


def _close_fraction(actions: list[str]) -> float:
    if "take_partial_profit" in actions:
        return 0.5
    if actions and actions[0] in {"close", "take_profit_hit"}:
        return 1.0
    return 0.0


def _has_reply_quote(text: str) -> bool:
    return any(label in text for label in ("回复:", "鍥炲:", "Reply:"))


def _media_only(text: str) -> bool:
    clean = _flat(text)
    has_image = "图片" in clean or "鍥剧墖" in clean
    return clean in {"[Photo]", "Photo"} or has_image and not _looks_like_new_signal(clean)


def _mentions_trade_intent(text: str) -> bool:
    return _looks_like_new_signal(_flat(text))


def _simple(
    message: NormalizedMessage,
    category: str,
    confidence: float,
    missing: list[str] | None = None,
) -> SignalCandidate:
    return SignalCandidate(
        source_log_id=message.log_id,
        category=category,
        raw_text=message.raw_text,
        evidence_text=_evidence(message.main_text),
        source_url=message.source_url,
        reply_url=message.reply_url,
        confidence=confidence,
        missing_fields=missing or [],
        status="needs_review" if missing else "parsed",
    )


def _map_symbol(symbol: str) -> tuple[str, str]:
    return SYMBOL_MAP.get(symbol.upper(), (symbol.upper(), f"{symbol.upper()}USDT"))


def _unique(values: list[float]) -> list[float]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _evidence(text: str) -> str:
    return " ".join(text.split())[:500]


def _flat(text: str) -> str:
    return " ".join(text.replace("\r", "\n").split())
