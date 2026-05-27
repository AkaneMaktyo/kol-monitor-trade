"""Replay action execution."""

import asyncio

from app.config import AppConfig
from app.persistence.replay_store import ReplayStore
from app.services.replay.inspector import build_live_context, inspect_log
from app.services.replay.query_service import clear_replay_query_cache
from app.signals.normalizer import is_gold_empire


class ReplayActionService:
    def __init__(self, config: AppConfig, store: ReplayStore, executor):
        self._config = config
        self._store = store
        self._executor = executor

    async def run_gold_empire(
        self,
        action: str,
        log_ids: list[str],
        confirmation_text: str = "",
    ) -> dict:
        if action not in {"preview", "persist", "real_execute"}:
            raise ValueError("不支持的回放动作")
        ids = _unique_ids(log_ids)
        if not ids:
            raise ValueError("至少选择一条记录")
        if action == "real_execute" and confirmation_text != "REAL_EXECUTE":
            raise ValueError("真实执行需要输入 REAL_EXECUTE")
        rows = await asyncio.to_thread(self._store.logs_by_ids, ids)
        if len(rows) != len(ids):
            raise ValueError("存在已失效或不存在的回放记录")
        if any(not is_gold_empire(row) for row in rows):
            raise ValueError("所选记录不属于 Gold Empire")
        live = build_live_context(self._config)
        if action == "real_execute":
            await self._precheck(rows, live)
            result = await self._execute_real(rows, live)
            clear_replay_query_cache()
            return result
        persist = action == "persist"
        results = []
        for row in rows:
            item = await inspect_log(
                self._config,
                self._executor,
                row,
                persist=persist,
                allow_submit=False,
                live_context=live,
            )
            results.append(_result(item))
        if persist:
            clear_replay_query_cache()
        return {"ok": True, "action": action, "total": len(results), "results": results}

    async def _precheck(self, rows: list[dict], live: dict) -> None:
        if not live.get("live_mode"):
            raise ValueError(live.get("disabled_reason") or "真实执行当前不可用")
        failures = []
        for row in rows:
            item = await inspect_log(self._config, self._executor, row, live_context=live)
            if not item["selectable_actions"]["real_execute"]:
                failures.append(f"{row.get('id')}: {item['selectable_actions']['real_execute_disabled_reason']}")
        if failures:
            raise ValueError("真实执行预检查未通过: " + " | ".join(failures[:3]))

    async def _execute_real(self, rows: list[dict], live: dict) -> dict:
        results = []
        for index, row in enumerate(rows, start=1):
            item = await inspect_log(
                self._config,
                self._executor,
                row,
                persist=True,
                allow_submit=True,
                current_time=True,
                live_context=live,
            )
            results.append(_result(item))
            if item["execution"]["status"] != "submitted":
                return {
                    "ok": False,
                    "action": "real_execute",
                    "total": len(results),
                    "stopped_at": index,
                    "results": results,
                }
        return {"ok": True, "action": "real_execute", "total": len(results), "results": results}


def _result(item: dict) -> dict:
    return {
        "log_id": item["log_id"],
        "candidate_status": item["candidate"]["status"],
        "execution_status": item["execution"]["status"],
        "item": item,
    }


def _unique_ids(log_ids: list[str]) -> list[str]:
    seen, result = set(), []
    for item in log_ids:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
