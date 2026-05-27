"""Simple in-memory TTL cache."""

from collections import OrderedDict
from threading import Lock
from time import monotonic


class TtlCache:
    def __init__(self, ttl_seconds: int, max_size: int = 128):
        self._ttl = max(1, ttl_seconds)
        self._max_size = max(1, max_size)
        self._items = OrderedDict()
        self._lock = Lock()

    def get(self, key):
        with self._lock:
            value = self._items.get(key)
            if not value:
                return None
            expires_at, payload = value
            if expires_at <= monotonic():
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return payload

    def set(self, key, value) -> None:
        with self._lock:
            self._items[key] = (monotonic() + self._ttl, value)
            self._items.move_to_end(key)
            self._trim()

    def pop(self, key) -> None:
        with self._lock:
            self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def _trim(self) -> None:
        now = monotonic()
        expired = [key for key, (expires_at, _) in self._items.items() if expires_at <= now]
        for key in expired:
            self._items.pop(key, None)
        while len(self._items) > self._max_size:
            self._items.popitem(last=False)
