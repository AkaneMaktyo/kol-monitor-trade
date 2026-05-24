"""Build safe trade update intents from parsed position updates."""

from app.signals.models import SignalCandidate
from app.trading.models import TradeUpdate

ACTIONABLE = {"close", "take_partial_profit", "move_stop_to_breakeven"}
AUDIT_ONLY = {"hold", "take_profit_hit"}
REVIEW_ONLY = {"add_layer", "risk_modifier"}


def build_update_intent(
    candidate: SignalCandidate,
    related_signal_id: str = "",
) -> TradeUpdate | None:
    if candidate.category != "position_update":
        return None
    reasons = _reasons(candidate, related_signal_id)
    return TradeUpdate(
        source_log_id=candidate.source_log_id,
        action=candidate.action,
        actions=candidate.actions or ([candidate.action] if candidate.action else []),
        reply_url=candidate.reply_url,
        related_signal_id=related_signal_id,
        action_text=candidate.action_text or candidate.evidence_text,
        close_fraction=candidate.close_fraction,
        dry_run=True,
        status=_status(candidate.action, reasons),
        reasons=reasons,
    )


def _reasons(candidate: SignalCandidate, related_signal_id: str) -> list[str]:
    action = candidate.action
    if not action:
        return ["missing_action"]
    if action in AUDIT_ONLY:
        return ["audit_only"]
    if action in REVIEW_ONLY:
        return ["manual_review_required"]
    reasons = []
    if action in ACTIONABLE and not candidate.reply_url:
        reasons.append("missing_reply_url")
    if action in ACTIONABLE and not related_signal_id:
        reasons.append("missing_related_signal")
    if action not in ACTIONABLE | AUDIT_ONLY | REVIEW_ONLY:
        reasons.append("unsupported_action")
    return reasons


def _status(action: str, reasons: list[str]) -> str:
    if not action:
        return "needs_review"
    if action in AUDIT_ONLY:
        return "audit_only"
    return "ready" if not reasons else "needs_review"
