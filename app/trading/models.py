"""Trading intent data objects."""

from dataclasses import dataclass, field


@dataclass
class TradeIntent:
    source_log_id: str
    exchange: str
    symbol: str
    side: str
    order_type: str
    entry_price: float
    quantity: float
    stop_loss: float
    take_profits: list[float] = field(default_factory=list)
    dry_run: bool = True
    status: str = "blocked"
    reasons: list[str] = field(default_factory=list)
    quote_risk_usdt: float = 0.0
    notional_usdt: float = 0.0
    account_equity_usdt: float = 0.0
    risk_percent: float = 0.0
    origin: str = ""
    origin_log_id: str = ""
    triggered_at: str = ""
    layer_index: int = 0
    layer_count: int = 1

    def to_dict(self) -> dict:
        return {
            "source_log_id": self.source_log_id,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "stop_loss": self.stop_loss,
            "take_profits": self.take_profits,
            "dry_run": self.dry_run,
            "status": self.status,
            "reasons": self.reasons,
            "quote_risk_usdt": self.quote_risk_usdt,
            "notional_usdt": self.notional_usdt,
            "account_equity_usdt": self.account_equity_usdt,
            "risk_percent": self.risk_percent,
            "origin": self.origin,
            "origin_log_id": self.origin_log_id,
            "triggered_at": self.triggered_at,
            "layer_index": self.layer_index,
            "layer_count": self.layer_count,
        }


@dataclass
class TradeUpdate:
    source_log_id: str
    action: str
    actions: list[str] = field(default_factory=list)
    reply_url: str = ""
    related_signal_id: str = ""
    action_text: str = ""
    close_fraction: float = 0.0
    dry_run: bool = True
    status: str = "needs_review"
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_log_id": self.source_log_id,
            "action": self.action,
            "actions": self.actions,
            "reply_url": self.reply_url,
            "related_signal_id": self.related_signal_id,
            "action_text": self.action_text,
            "close_fraction": self.close_fraction,
            "dry_run": self.dry_run,
            "status": self.status,
            "reasons": self.reasons,
        }
