"""Risk gate for historical chain tests."""

from dataclasses import dataclass
from datetime import datetime, timezone
from math import floor

from app.config import TradingConfig
from app.signals.models import SignalCandidate
from app.trading.models import TradeIntent

MIN_QTY = 0.01
QTY_STEP = 0.01
DEFAULT_EQUITY_USDT = 100.0
DEFAULT_RISK_PERCENT = 5.0


@dataclass(frozen=True)
class RiskBudget:
    account_equity_usdt: float
    risk_percent: float
    quote_risk_usdt: float


def describe_risk_budget(config: TradingConfig | None) -> dict:
    budget = _risk_budget(config)
    return {"account_equity_usdt": budget.account_equity_usdt, "risk_percent": budget.risk_percent, "quote_risk_usdt": budget.quote_risk_usdt}


def build_dry_run_intent(candidate: SignalCandidate, message_time: str, config: TradingConfig | None = None, now: datetime | None = None, ignore_stale: bool = False, market_price: float = 0.0) -> TradeIntent | None:
    intents = build_dry_run_intents(candidate, message_time, config, now, ignore_stale, market_price)
    return intents[0] if intents else None


def build_dry_run_intents(candidate: SignalCandidate, message_time: str, config: TradingConfig | None = None, now: datetime | None = None, ignore_stale: bool = False, market_price: float = 0.0) -> list[TradeIntent]:
    if candidate.category != "new_signal":
        return []
    entries = _entries(candidate, market_price)
    budget = _risk_budget(config)
    sizing_entry = _sizing_entry(entries)
    sizing_stop = _sizing_stop(candidate, sizing_entry, budget)
    reasons = _base_reasons(candidate, sizing_entry, sizing_stop, budget)
    stale = "" if ignore_stale else _stale_reason(message_time, now or datetime.now(timezone.utc), config.max_signal_age_seconds if config else 900)
    if stale:
        reasons.append(stale)
    total_qty = _quantity(sizing_entry, sizing_stop, budget.quote_risk_usdt)
    quantities = _split_quantities(total_qty, len(entries))
    if len(entries) > 1 and any(qty < MIN_QTY for qty in quantities):
        reasons.append("quantity_below_min")
    status = "ready" if not reasons else "blocked"
    return [
        TradeIntent(
            source_log_id=candidate.source_log_id,
            exchange="bitget",
            symbol=candidate.bitget_symbol,
            side=candidate.side,
            order_type=candidate.entry_order_type,
            entry_price=entry,
            quantity=qty,
            stop_loss=candidate.stop_loss or 0.0,
            take_profits=candidate.take_profits,
            dry_run=True,
            status=status,
            reasons=reasons,
            quote_risk_usdt=_layer_risk(entry, candidate.stop_loss or sizing_stop, qty),
            notional_usdt=round(entry * qty, 2) if entry else 0.0,
            account_equity_usdt=budget.account_equity_usdt,
            risk_percent=budget.risk_percent,
            layer_index=index,
            layer_count=len(entries),
        )
        for index, (entry, qty) in enumerate(zip(entries, quantities))
    ]


def _base_reasons(candidate: SignalCandidate, entry: float, sizing_stop: float, budget: RiskBudget) -> list[str]:
    reasons = []
    if candidate.confidence < 0.9:
        reasons.append("low_confidence")
    reasons.extend(_required_field_reasons(candidate))
    if not candidate.bitget_symbol:
        reasons.append("missing_bitget_symbol")
    if entry <= 0:
        reasons.append("invalid_entry")
    if entry and candidate.stop_loss and _wrong_stop_side(candidate.side, entry, candidate.stop_loss):
        reasons.append("stop_loss_wrong_side")
    reasons.extend(_risk_reasons(budget))
    if entry and sizing_stop and _quantity(entry, sizing_stop, budget.quote_risk_usdt) < MIN_QTY:
        reasons.append("quantity_below_min")
    return _unique(reasons)


def _risk_budget(config: TradingConfig | None) -> RiskBudget:
    equity = config.account_equity_usdt if config else DEFAULT_EQUITY_USDT
    percent = config.max_stop_loss_percent if config else DEFAULT_RISK_PERCENT
    risk_usdt = max(equity, 0.0) * max(percent, 0.0) / 100
    cap = config.max_order_risk_usdt if config else 0.0
    if cap > 0:
        risk_usdt = min(risk_usdt, cap)
    return RiskBudget(round(equity, 8), round(percent, 4), round(risk_usdt, 8))


def _risk_reasons(budget: RiskBudget) -> list[str]:
    reasons = []
    if budget.account_equity_usdt <= 0:
        reasons.append("invalid_account_equity")
    if budget.risk_percent <= 0 or budget.risk_percent > 100:
        reasons.append("invalid_risk_percent")
    if not reasons and budget.quote_risk_usdt <= 0:
        reasons.append("invalid_risk_amount")
    return reasons


def _wrong_stop_side(side: str, entry: float, stop: float) -> bool:
    return stop >= entry if side == "long" else stop <= entry if side == "short" else True


def _quantity(entry: float, stop: float, risk_usdt: float) -> float:
    distance = abs(entry - stop)
    if distance <= 0:
        return 0.0
    return round(floor((risk_usdt / distance) / QTY_STEP) * QTY_STEP, 2)


def _stale_reason(message_time: str, now: datetime, max_age_seconds: int) -> str:
    try:
        parsed = datetime.strptime(message_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return "unknown_signal_time"
    return "historical_signal_stale" if (now - parsed).total_seconds() > max_age_seconds else ""


def _entries(candidate: SignalCandidate, market_price: float) -> list[float]:
    if candidate.entry_numbers:
        return candidate.entry_numbers
    return [max(market_price, 0.0)] if candidate.entry_order_type == "market" else [0.0]


def _required_field_reasons(candidate: SignalCandidate) -> list[str]:
    return [f"missing_{item}" for item in candidate.missing_fields if item not in {"take_profit", "stop_loss"}]


def _sizing_stop(candidate: SignalCandidate, entry: float, budget: RiskBudget) -> float:
    if entry <= 0:
        return 0.0
    if candidate.stop_loss and candidate.stop_loss > 0:
        return candidate.stop_loss
    distance = entry * budget.risk_percent / 100
    if distance <= 0:
        return 0.0
    return entry - distance if candidate.side == "long" else entry + distance


def _sizing_entry(entries: list[float]) -> float:
    valid = [entry for entry in entries if entry > 0]
    return round(sum(valid) / len(valid), 8) if valid else 0.0


def _split_quantities(total_qty: float, count: int) -> list[float]:
    if count <= 1:
        return [round(total_qty, 2)]
    steps = int(floor(total_qty / QTY_STEP))
    base, extra = divmod(steps, count)
    values = [base * QTY_STEP for _ in range(count)]
    for index in range(extra):
        values[index] = round(values[index] + QTY_STEP, 2)
    return [round(value, 2) for value in values]


def _layer_risk(entry: float, stop: float, quantity: float) -> float:
    return round(abs(float(entry or 0) - float(stop or 0)) * float(quantity or 0), 8)


def _unique(items: list[str]) -> list[str]:
    result = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result
