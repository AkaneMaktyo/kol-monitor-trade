"""Historical signal chain replay service."""

import asyncio
from collections import Counter

from app.config import WxPusherConfig
from app.persistence.store import LogStore
from app.services.wxpusher.detail import fetch_detail_text
from app.signals.normalizer import detail_url, is_gold_empire, normalize_entry
from app.signals.parser import parse_signal


class HistoricalSignalChain:
    def __init__(self, store: LogStore, wxpusher: WxPusherConfig, executor=None):
        self._store = store
        self._wxpusher = wxpusher
        self._executor = executor

    async def replay_gold_empire(
        self,
        limit: int = 120,
        persist: bool = False,
        ignore_stale: bool = False,
    ) -> dict:
        rows = await asyncio.to_thread(self._store.list_logs, min(limit, 500), "", "wxpusher")
        rows = [row for row in reversed(rows) if is_gold_empire(row)]
        seen = set()
        candidates = []
        intents = []
        updates = []
        details_fetched = 0
        detail_failures = 0
        for row in rows:
            key = self._dedupe_key(row)
            if key in seen:
                continue
            seen.add(key)
            detail = await self._detail_if_needed(row)
            if detail:
                details_fetched += 1
            elif "..." in row.get("content", "") and detail_url(row):
                detail_failures += 1
            message = normalize_entry(row, detail)
            candidate = parse_signal(message)
            candidates.append(candidate)
            execution = self._execution(candidate, row, persist, ignore_stale)
            if execution.get("intent"):
                intents.append(execution["intent"])
            if execution.get("update"):
                updates.append(execution["update"])
        return self._result(candidates, intents, updates, details_fetched, detail_failures)

    def _execution(self, candidate, row: dict, persist: bool, ignore_stale: bool) -> dict:
        if self._executor:
            return self._executor.handle_candidate(
                candidate,
                row.get("timestamp", ""),
                persist=persist,
                ignore_stale=ignore_stale,
                allow_submit=False,
            )
        return {"intent": None}

    async def _detail_if_needed(self, row: dict) -> str:
        url = detail_url(row)
        if not url or "..." not in row.get("content", ""):
            return ""
        try:
            return await fetch_detail_text(url, self._wxpusher)
        except Exception:
            return ""

    @staticmethod
    def _dedupe_key(row: dict) -> str:
        content = row.get("content", "")
        for label in ("原文:", "详情:"):
            for line in content.splitlines():
                if line.startswith(label):
                    return line.split(":", 1)[1].strip()
        return row.get("id", "")

    @staticmethod
    def _result(candidates, intents, updates, details_fetched: int, detail_failures: int) -> dict:
        categories = Counter(item.category for item in candidates)
        statuses = Counter(item.status for item in candidates)
        intent_statuses = Counter(item.get("status", "") for item in intents)
        update_statuses = Counter(item.get("status", "") for item in updates)
        update_actions = Counter(item.get("action", "") for item in updates)
        return {
            "summary": {
                "unique_messages": len(candidates),
                "details_fetched": details_fetched,
                "detail_failures": detail_failures,
                "categories": dict(categories),
                "candidate_statuses": dict(statuses),
                "trade_intents": len(intents),
                "intent_statuses": dict(intent_statuses),
                "signal_updates": len(updates),
                "update_statuses": dict(update_statuses),
                "update_actions": dict(update_actions),
            },
            "candidates": [item.to_dict() for item in candidates],
            "trade_intents": intents,
            "signal_updates": updates,
        }
