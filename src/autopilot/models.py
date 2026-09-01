"""Repository functions (APK-faithful: sessions keyed by URL target)."""

import uuid
from datetime import datetime, timezone

from autopilot.database import Database
from autopilot.domain.enums import SessionStatus
from autopilot.domain.schemas import AutomationConfig


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, url: str, name: str, config: AutomationConfig) -> dict:
        session_id = uuid.uuid4().hex[:12]
        now = _now()
        await self.db.execute(
            """INSERT INTO sessions
               (id, url, name, status, mode, tab_count, refresh_interval_sec,
                scroll_interval_sec, enable_proxy, enable_spoofing,
                randomize_intervals, custom_js, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session_id,
                url,
                name,
                SessionStatus.IDLE.value,
                config.mode.value,
                config.tab_count,
                config.refresh_interval_sec,
                config.scroll_interval_sec,
                int(config.enable_proxy),
                int(config.enable_spoofing),
                int(config.randomize_intervals),
                config.custom_js,
                now,
                now,
            ),
        )
        await self.db.execute(
            "INSERT INTO session_stats (session_id, start_time, last_active) VALUES (?,?,?)",
            (session_id, now, now),
        )
        return {"id": session_id, "url": url, "name": name, "status": "idle"}

    async def get(self, session_id: str) -> dict | None:
        row = await self.db.fetchone("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return dict(row) if row else None

    async def list(self) -> list[dict]:
        rows = await self.db.fetchall("SELECT * FROM sessions ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    async def update_status(self, session_id: str, status: str) -> None:
        await self.db.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), session_id),
        )

    async def update_config(self, session_id: str, config: AutomationConfig) -> None:
        await self.db.execute(
            """UPDATE sessions SET mode=?, tab_count=?, refresh_interval_sec=?,
               scroll_interval_sec=?, enable_proxy=?, enable_spoofing=?,
               randomize_intervals=?, custom_js=?, updated_at=? WHERE id=?""",
            (
                config.mode.value,
                config.tab_count,
                config.refresh_interval_sec,
                config.scroll_interval_sec,
                int(config.enable_proxy),
                int(config.enable_spoofing),
                int(config.randomize_intervals),
                config.custom_js,
                _now(),
                session_id,
            ),
        )

    async def delete(self, session_id: str) -> None:
        await self.db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await self.db.execute("DELETE FROM session_stats WHERE session_id = ?", (session_id,))


class StatsRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self, session_id: str) -> dict | None:
        row = await self.db.fetchone(
            "SELECT * FROM session_stats WHERE session_id = ?", (session_id,)
        )
        return dict(row) if row else None

    async def increment(self, session_id: str, field: str, amount: int = 1) -> None:
        allowed = {
            "pages_loaded",
            "scrolls_performed",
            "tabs_switched",
            "js_executions",
            "errors",
        }
        if field not in allowed:
            raise ValueError(f"Unknown stat field: {field}")
        await self.db.execute(
            f"UPDATE session_stats SET {field} = {field} + ?, last_active = ? WHERE session_id = ?",
            (amount, _now(), session_id),
        )


class ProxyRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def upsert(self, url: str, protocol: str, country: str | None = None) -> None:
        await self.db.execute(
            """INSERT INTO proxy_pool (url, protocol, country, is_active, last_checked)
               VALUES (?,?,?,0,?) ON CONFLICT(url) DO NOTHING""",
            (url, protocol, country, _now()),
        )

    async def set_active(self, url: str, active: bool, latency_ms: int | None = None) -> None:
        await self.db.execute(
            "UPDATE proxy_pool SET is_active=?, latency_ms=?, last_checked=?, fail_count=0 WHERE url=?",
            (int(active), latency_ms, _now(), url),
        )

    async def set_inactive(self, url: str) -> None:
        await self.db.execute(
            "UPDATE proxy_pool SET is_active=0, fail_count=fail_count+1, last_checked=? WHERE url=?",
            (_now(), url),
        )

    async def active(self) -> list[dict]:
        rows = await self.db.fetchall(
            "SELECT * FROM proxy_pool WHERE is_active=1 ORDER BY latency_ms ASC"
        )
        return [dict(r) for r in rows]

    async def count(self) -> int:
        row = await self.db.fetchone(
            "SELECT COUNT(*) AS c FROM proxy_pool WHERE is_active=1"
        )
        return row["c"] if row else 0


class UserRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def upsert(self, user_id: int, username: str | None, is_admin: bool) -> None:
        await self.db.execute(
            """INSERT INTO bot_users (user_id, username, is_admin, created_at)
               VALUES (?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
                   is_admin=excluded.is_admin""",
            (user_id, username, int(is_admin), _now()),
        )