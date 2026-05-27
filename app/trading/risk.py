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
    return {
        "account_equity_usdt": budget.account_equity_usdt,
        "risk_percent": budget.risk_percent,
        "quote_risk_usdt": budget.quote_risk_usdt,
    }


def build_dry_run_intent(
    candidate: SignalCandidate,
    message_time: str,
    config: TradingConfig | None = None,
    now: datetime | None = None,
    ignore_stale: bool = False,
    market_price: float = 0.0,
) -> TradeIntent | None:
    if candidate.category != "new_signal":
        return None
    entry = _entry_price(candidate, market_price)
    budget = _risk_budget(config)
    sizing_stop = _sizing_stop(candidate, entry, budget)
    reasons = _base_reasons(candidate, entry, sizing_stop, budget)
    max_age = config.max_signal_age_seconds if config else 900
    stale = "" if ignore_stale else _stale_reason(message_time, now or datetime.now(timezone.utc), max_age)
    if stale:
        reasons.append(stale)
    quantity = _quantity(entry, sizing_stop, budget.quote_risk_usdt)
    status = "ready" if not reasons else "blocked"
    return TradeIntent(
        source_log_id=candidate.source_log_id,
        exchange="bitget",
        symbol=candidate.bitget_symbol,
        side=candidate.side,
        order_type=candidate.entry_order_type,
        entry_price=entry,
        quantity=quantity,
        stop_loss=candidate.stop_loss or 0.0,
        take_profits=candidate.take_profits,
        dry_run=True,
        status=status,
        reasons=reasons,
        quote_risk_usdt=budget.quote_risk_usdt if quantity >= MIN_QTY else 0.0,
        notional_usdt=round(entry * quantity, 2) if entry else 0.0,
        account_equity_usdt=budget.account_equity_usdt,
        risk_percent=budget.risk_percent,
    )


def _base_reasons(
    candidate: SignalCandidate,
    entry: float,
    sizing_stop: float,
    budget: RiskBudget,
) -> list[str]:
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
    return reasons


def _risk_budget(config: TradingConfig | None) -> RiskBudget:
    equity = config.account_equity_usdt if config else DEFAULT_EQUITY_USDT
    percent = config.max_stop_loss_percent if config else DEFAULT_RISK_PERCENT
    risk_usdt = max(equity, 0.0) * max(percent, 0.0) / 100
    cap = config.max_order_risk_usdt if config else 0.0
    if cap > 0:
        risk_usdt = min(risk_usdt, cap)
    return RiskBudget(
        account_equity_usdt=round(equity, 8),
        risk_percent=round(percent, 4),
        quote_risk_usdt=round(risk_usdt, 8),
    )


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
    if side == "long":
        return stop >= entry
    if side == "short":
        return stop <= entry
    return True


def _quantity(entry: float, stop: float, risk_usdt: float) -> float:
    distance = abs(entry - stop)
    if distance <= 0:
        return 0.0
    raw = risk_usdt / distance
    return round(floor(raw / QTY_STEP) * QTY_STEP, 2)


def _stale_reason(message_time: str, now: datetime, max_age_seconds: int) -> str:
    try:
        parsed = datetime.strptime(message_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return "unknown_signal_time"
    age = (now - parsed).total_seconds()
    return "historical_signal_stale" if age > max_age_seconds else ""


def _entry_price(candidate: SignalCandidate, market_price: float) -> float:
    if candidate.entry_numbers:
        return candidate.entry_numbers[0]
    if candidate.entry_order_type == "market":
        return max(market_price, 0.0)
    return 0.0


def _required_field_reasons(candidate: SignalCandidate) -> list[str]:
    allowed = {"take_profit", "stop_loss"}
    return [f"missing_{item}" for item in candidate.missing_fields if item not in allowed]


def _sizing_stop(candidate: SignalCandidate, entry: float, budget: RiskBudget) -> float:
    if entry <= 0:
        return 0.0
    if candidate.stop_loss and candidate.stop_loss > 0:
        return candidate.stop_loss
    distance = entry * budget.risk_percent / 100
    if distance <= 0:
        return 0.0
    return entry - distance if candidate.side == "long" else entry + distance
