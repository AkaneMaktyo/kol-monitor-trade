"""Bitget helper functions."""

import base64
import hashlib
import hmac
from urllib.parse import urlencode


def signature(secret: str, timestamp: str, method: str, path: str, body: str) -> str:
    payload = f"{timestamp}{method}{path}{body}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def order_result(response: dict, client_oid: str) -> dict:
    data = response.get("data") or {}
    ok = response.get("code") == "00000"
    return {
        "exchange": "bitget",
        "status": "submitted" if ok else "failed",
        "client_oid": client_oid,
        "order_id": str(data.get("orderId") or ""),
        "error": "" if ok else str(response.get("msg") or response.get("code") or ""),
        "raw": response,
    }


def num(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".")


def query(values: dict | None) -> str:
    return f"?{urlencode(values)}" if values else ""


def as_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def first_take_profit(intent) -> float:
    for item in getattr(intent, "take_profits", []) or []:
        value = as_float(item)
        if value > 0:
            return value
    return 0.0


def position_tpsl_body(intent, product_type: str, margin_coin: str, client_oid: str) -> dict:
    body = {
        "marginCoin": margin_coin,
        "productType": product_type,
        "symbol": intent.symbol,
        "holdSide": intent.side,
    }
    take_profit = first_take_profit(intent)
    stop_loss = as_float(getattr(intent, "stop_loss", 0))
    if take_profit > 0:
        body.update(
            stopSurplusTriggerPrice=num(take_profit),
            stopSurplusTriggerType="mark_price",
            stopSurplusExecutePrice=num(take_profit),
            stopSurplusClientOid=f"{client_oid}_tp"[:64],
        )
    if stop_loss > 0:
        body.update(
            stopLossTriggerPrice=num(stop_loss),
            stopLossTriggerType="mark_price",
            stopLossExecutePrice=num(stop_loss),
            stopLossClientOid=f"{client_oid}_sl"[:64],
        )
    return body if len(body) > 4 else {}


def tpsl_result(response: dict, client_oid: str) -> dict:
    rows = response.get("data") or []
    ok = response.get("code") == "00000"
    return {
        "status": "submitted" if ok else "failed",
        "client_oid": client_oid,
        "order_ids": [str(item.get("orderId") or "") for item in rows if isinstance(item, dict)],
        "error": "" if ok else str(response.get("msg") or response.get("code") or ""),
        "raw": response,
    }
