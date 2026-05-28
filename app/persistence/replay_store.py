"""Replay query storage helpers."""

import re

from app.config import MySQLConfig
from app.persistence import connect_mysql


class ReplayStore:
    def __init__(self, config: MySQLConfig):
        self._config = config

    def recent_wxpusher(
        self,
        limit: int = 200,
        author: str = "",
        source_channel: str = "",
        date_from: str = "",
        date_to: str = "",
    ) -> list[dict]:
        where, params = self._filters(author, source_channel, date_from, date_to)
        sql = f"""
            SELECT * FROM log_entries
            WHERE platform='wxpusher' {where}
            ORDER BY timestamp DESC
            LIMIT %s
        """
        return self._fetch(sql, [*params, max(1, min(limit, 500))])

    def logs_by_ids(self, log_ids: list[str]) -> list[dict]:
        ids = [item for item in log_ids if item]
        if not ids:
            return []
        placeholders = ", ".join(["%s"] * len(ids))
        sql = f"SELECT * FROM log_entries WHERE id IN ({placeholders})"
        rows = self._fetch(sql, ids)
        mapping = {row["id"]: row for row in rows}
        return [mapping[item] for item in ids if item in mapping]

    def _fetch(self, sql: str, params: list) -> list[dict]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]

    def _connect(self):
        return connect_mysql(self._config)

    @staticmethod
    def _filters(
        author: str,
        source_channel: str,
        date_from: str,
        date_to: str,
    ) -> tuple[str, list[str]]:
        clauses, params = [], []
        if author:
            clauses.append("author LIKE %s")
            params.append(f"%{author}%")
        if source_channel:
            clauses.append("source_channel LIKE %s")
            params.append(f"%{source_channel}%")
        if _valid_day(date_from):
            clauses.append("timestamp >= %s")
            params.append(f"{date_from} 00:00:00")
        if _valid_day(date_to):
            clauses.append("timestamp <= %s")
            params.append(f"{date_to} 23:59:59")
        return (" AND " + " AND ".join(clauses), params) if clauses else ("", params)


def _valid_day(value: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", value or ""))
