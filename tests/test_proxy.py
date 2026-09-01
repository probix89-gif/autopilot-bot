"""Tests: proxy pool logic."""

import pytest

from autopilot.engine.proxy_manager import ProxyManager, ProxyEntry


def test_parse_custom():
    mgr = ProxyManager(sources=[], custom_proxies=["http://u:p@1.2.3.4:8080", "5.6.7.8:3128"])
    parsed = mgr._parse_custom(mgr.custom_proxies)
    assert len(parsed) == 2
    assert parsed[0].url == "http://u:p@1.2.3.4:8080"
    assert "5.6.7.8" in parsed[1].url


@pytest.mark.asyncio
async def test_get_many_returns_count():
    mgr = ProxyManager(sources=[])
    mgr._pool = [
        ProxyEntry(url="http://a:1", is_active=True),
        ProxyEntry(url="http://b:2", is_active=True),
        ProxyEntry(url="http://c:3", is_active=True),
    ]
    items = await mgr.get_many(2)
    assert len(items) == 2


@pytest.mark.asyncio
async def test_mark_bad_deactivates():
    mgr = ProxyManager(sources=[])
    mgr._pool = [ProxyEntry(url="http://bad:8080", is_active=True)]
    for _ in range(3):
        await mgr.mark_bad("http://bad:8080")
    assert mgr._pool[0].is_active is False
