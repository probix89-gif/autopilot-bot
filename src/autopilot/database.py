"""Async SQLite database layer."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'idle',
    mode TEXT NOT NULL DEFAULT 'simple_scroll',
    tab_count INTEGER NOT NULL DEFAULT 5,
    refresh_interval_sec INTEGER NOT NULL DEFAULT 30,
    scroll_interval_sec INTEGER NOT NULL DEFAULT 10,
    enable_proxy INTEGER NOT NULL DEFAULT 0,
    enable_spoofing INTEGER NOT NULL DEFAULT 0,
    randomize_intervals INTEGER NOT NULL DEFAULT 1,
    custom_js TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    pages_loaded INTEGER NOT NULL DEFAULT 0,
    scrolls_performed INTEGER NOT NULL DEFAULT 0,
    tabs_switched INTEGER NOT NULL DEFAULT 0,
    js_executions INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    start_time TEXT,
    last_active TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS proxy_pool (
    url TEXT PRIMARY KEY,
    protocol TEXT NOT NULL DEFAULT 'http',
    country TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    last_checked TEXT,
    fail_count INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER
);

CREATE TABLE IF NOT EXISTS bot_users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = str(Path(db_path))
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()
        logger.info("Database ready at %s", self.db_path)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple = ()):
        if self._conn is None:
            raise RuntimeError("Database not connected")
        cur = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cur

    async def fetchall(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
        cur = await self.execute(sql, params)
        rows = await cur.fetchall()
        await cur.close()
        return rows

    async def fetchone(self, sql: str, params: tuple = ()) -> aiosqlite.Row | None:
        cur = await self.execute(sql, params)
        row = await cur.fetchone()
        await cur.close()
        return row