"""持久化模块。"""

from contextlib import contextmanager
from threading import Lock, get_ident

import pymysql
from pymysql.cursors import DictCursor

from app.config import MySQLConfig

_POOL = {}
_LOCK = Lock()


def connect_mysql(
    config: MySQLConfig,
    *,
    database: str | None = None,
    use_database: bool = True,
):
    target = database if database is not None else config.database if use_database else None
    return _mysql_context(config, target)


def close_mysql_pool() -> None:
    with _LOCK:
        items = list(_POOL.values())
        _POOL.clear()
    for conn in items:
        try:
            conn.close()
        except Exception:
            continue


@contextmanager
def _mysql_context(config: MySQLConfig, database: str | None):
    key = _pool_key(config, database)
    conn = _ensure_connection(config, database, key)
    try:
        yield conn
    except Exception:
        _drop_connection(key)
        raise


def _ensure_connection(config: MySQLConfig, database: str | None, key: tuple):
    with _LOCK:
        conn = _POOL.get(key)
        if conn is None or not getattr(conn, "open", False):
            conn = _open_connection(config, database)
            _POOL[key] = conn
    try:
        conn.ping(reconnect=True)
        return conn
    except Exception:
        _drop_connection(key)
    conn = _open_connection(config, database)
    with _LOCK:
        _POOL[key] = conn
    return conn


def _drop_connection(key: tuple) -> None:
    with _LOCK:
        conn = _POOL.pop(key, None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


def _open_connection(config: MySQLConfig, database: str | None):
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=database,
        charset=config.charset,
        autocommit=True,
        cursorclass=DictCursor,
    )


def _pool_key(config: MySQLConfig, database: str | None) -> tuple:
    return (
        get_ident(),
        config.host,
        config.port,
        config.user,
        config.charset,
        database or "",
    )
