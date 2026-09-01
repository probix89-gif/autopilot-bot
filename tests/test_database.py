"""Tests: DB repositories (in-memory SQLite)."""

import pytest
import pytest_asyncio

from autopilot.database import Database
from autopilot.domain.schemas import AutomationConfig
from autopilot.models import SessionRepo, StatsRepo, ProxyRepo, UserRepo


@pytest_asyncio.fixture
async def db(tmp_path):
    d = Database(f"{tmp_path}/test.db")
    await d.connect()
    yield d
    await d.close()


@pytest.mark.asyncio
async def test_create_get_session(db):
    repo = SessionRepo(db)
    r = await repo.create("https://yo.fan/p/pb8nDtbKsfe", "my page", AutomationConfig())
    assert r["id"]
    row = await repo.get(r["id"])
    assert row["url"] == "https://yo.fan/p/pb8nDtbKsfe"
    assert row["tab_count"] == 5


@pytest.mark.asyncio
async def test_update_config(db):
    repo = SessionRepo(db)
    r = await repo.create("https://yo.fan/p/xyz", "", AutomationConfig())
    cfg = AutomationConfig(mode="deep_scroll", tab_count=7)
    await repo.update_config(r["id"], cfg)
    row = await repo.get(r["id"])
    assert row["mode"] == "deep_scroll"
    assert row["tab_count"] == 7


@pytest.mark.asyncio
async def test_stats(db):
    repo = SessionRepo(db)
    sr = StatsRepo(db)
    r = await repo.create("https://yo.fan/p/xyz", "", AutomationConfig())
    await sr.increment(r["id"], "scrolls_performed", 10)
    s = await sr.get(r["id"])
    assert s["scrolls_performed"] == 10


@pytest.mark.asyncio
async def test_delete_cascades(db):
    repo = SessionRepo(db)
    sr = StatsRepo(db)
    r = await repo.create("https://yo.fan/p/xyz", "", AutomationConfig())
    await repo.delete(r["id"])
    assert await repo.get(r["id"]) is None
    assert await sr.get(r["id"]) is None
