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
