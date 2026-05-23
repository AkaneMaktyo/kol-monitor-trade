"""Rule-based parser for high-confidence trading signals."""

import re

from app.signals.models import NormalizedMessage, SignalCandidate

UPDATE_RULES = [
    ("move_stop_to_breakeven", r"\b(set\s*b\.?e\.?|breakeven|break even)\b"),
    ("take_partial_profit", r"\b(booked half|close first|partial|half profits?)\b"),
    ("hold", r"\b(hold last|keep holding|let it run)\b"),
    ("risk_modifier", r"\b(risk half|half of normal risk)\b"),
    ("add_layer", r"\b(more buy|more sell|second entry|enter again)\b"),
]

SYMBOL_MAP = {
    "GOLD": ("XAUUSD", "XAUUSDT"),
    "XAU": ("XAUUSD", "XAUUSDT"),
    "XAUUSD": ("XAUUSD", "XAUUSDT"),
}


def parse_signal(message: NormalizedMessage) -> SignalCandidate:
    text = message.main_text
    action = _update_action(text)
    if action:
        return SignalCandidate(
            source_log_id=message.log_id,
            category="position_update",
            raw_text=message.raw_text,
            evidence_text=_evidence(text),
            source_url=message.source_url,
            action=action,
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


def _update_action(text: str) -> str:
    clean = _flat(text)
    if "回复:" not in text and "Reply:" not in text and not _standalone_update(clean):
        return ""
    for action, pattern in UPDATE_RULES:
        if re.search(pattern, clean, flags=re.I):
            return action
    return ""


def _standalone_update(text: str) -> bool:
    return bool(re.search(r"\b(breakeven|booked half|hold last|risk half)\b", text, flags=re.I))


def _has_reply_quote(text: str) -> bool:
    return "回复:" in text or "Reply:" in text


def _media_only(text: str) -> bool:
    clean = _flat(text)
    return clean in {"[Photo]", "Photo"} or "图片" in clean and not _looks_like_new_signal(clean)


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
