"""HTTP helpers for direct WxPusher access."""

from urllib.request import ProxyHandler, build_opener


def open_direct(request, timeout: int = 20):
    opener = build_opener(ProxyHandler({}))
    return opener.open(request, timeout=timeout)
