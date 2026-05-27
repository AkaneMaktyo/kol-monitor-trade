"""Replay query assembly."""

import asyncio
from copy import deepcopy
from collections import Counter

from app.config import AppConfig
from app.persistence.replay_store import ReplayStore
from app.services.cache import TtlCache
from app.services.replay.inspector import build_live_context, inspect_log, replay_key
from app.signals.normalizer import is_gold_empire

_QUERY_CACHE = TtlCache(ttl_seconds=20, max_size=24)


class ReplayQueryService:
    def __init__(self, config: AppConfig, store: ReplayStore, executor):
        self._config = config
        self._store = store
        self._executor = executor

    async def load_gold_empire(
        self,
        *,
        author: str = "",
        source_channel: str = "",
        candidate_status: str = "",
        execution_status: str = "",
        limit: int = 120,
    ) -> dict:
        size = max(1, min(limit, 120))
        cache_key = _cache_key(author, source_channel, candidate_status, execution_status, size)
        cached = _QUERY_CACHE.get(cache_key)
        if cached is not None:
            return deepcopy(cached)
        fetch_limit = min(max(size * 4, 200), 500)
        rows = await asyncio.to_thread(
            self._store.recent_wxpusher,
            fetch_limit,
            author,
            source_channel,
        )
        live = build_live_context(self._config)
        seen, items = set(), []
        for row in rows:
            if not is_gold_empire(row):
                continue
            key = replay_key(row)
            if key in seen:
                continue
            seen.add(key)
            item = await inspect_log(self._config, self._executor, row, live_context=live)
            if candidate_status and item["candidate"]["status"] != candidate_status:
                continue
            if execution_status and item["execution"]["status"] != execution_status:
                continue
            items.append(item)
            if len(items) >= size:
                break
        payload = {
            "filters": {
                "author": author,
                "source_channel": source_channel,
                "candidate_status": candidate_status,
                "execution_status": execution_status,
                "limit": size,
            },
            "readiness": live,
            "summary": _summary(items),
            "items": items,
        }
        _QUERY_CACHE.set(cache_key, payload)
        return deepcopy(payload)


def clear_replay_query_cache() -> None:
    _QUERY_CACHE.clear()


def _summary(items: list[dict]) -> dict:
    candidate = Counter(item["candidate"]["status"] for item in items)
    execution = Counter(item["execution"]["status"] for item in items)
    return {
        "total": len(items),
        "candidate_statuses": dict(candidate),
        "execution_statuses": dict(execution),
        "real_executable": sum(1 for item in items if item["selectable_actions"]["batch_selectable"]),
    }


def _cache_key(
    author: str,
    source_channel: str,
    candidate_status: str,
    execution_status: str,
    limit: int,
) -> tuple[str, str, str, str, int]:
    return (
        author.strip(),
        source_channel.strip(),
        candidate_status.strip(),
        execution_status.strip(),
        limit,
    )
