"""Signal parsing data objects."""

from dataclasses import dataclass, field


@dataclass
class NormalizedMessage:
    log_id: str
    timestamp: str
    raw_text: str
    main_text: str
    source_url: str = ""
    detail_url: str = ""
    source_channel: str = ""
    author: str = ""
    dedupe_key: str = ""
    detail_fetched: bool = False


@dataclass
class SignalCandidate:
    source_log_id: str
    category: str
    raw_text: str
    evidence_text: str = ""
    source_url: str = ""
    symbol: str = ""
    bitget_symbol: str = ""
    side: str = ""
    entry_numbers: list[float] = field(default_factory=list)
    take_profits: list[float] = field(default_factory=list)
    stop_loss: float | None = None
    confidence: float = 0.0
    missing_fields: list[str] = field(default_factory=list)
    action: str = ""
    status: str = "needs_review"

    def to_dict(self) -> dict:
        return {
            "source_log_id": self.source_log_id,
            "category": self.category,
            "source_url": self.source_url,
            "symbol": self.symbol,
            "bitget_symbol": self.bitget_symbol,
            "side": self.side,
            "entry_numbers": self.entry_numbers,
            "take_profits": self.take_profits,
            "stop_loss": self.stop_loss,
            "confidence": self.confidence,
            "missing_fields": self.missing_fields,
            "action": self.action,
            "status": self.status,
            "evidence_text": self.evidence_text,
        }
