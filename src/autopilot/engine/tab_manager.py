"""Playwright browser manager — APK's TabManager faithful port.

Each tab is a Playwright BrowserContext with its own profile, proxy,
and stealth injection. The TabManager (U2.c) owns the contexts and
provides methods to create, navigate, scroll, and destroy them.
"""

import asyncio
import logging
import random
from typing import Any

logger = logging.getLogger(__name__)

# Human-like timing helpers (APK-faithful)
# Y2.a.b(mean, deviation, min, max) → gaussian-ish random in range
def _rand_between(mean: float, dev: float, lo: float, hi: float) -> float:
    val = random.gauss(mean, dev)
    return max(lo, min(hi, val))


def _rand_chance(pct: int) -> bool:
    return random.randint(1, 100) <= pct


class Tab:
    """Wraps a single Playwright context (APK's V2.r)."""

    def __init__(self, context: Any, tab_id: str, index: int, url: str) -> None:
        self.context = context
        self.tab_id = tab_id
        self.index = index
        self.url = url
        self.page: Any | None = None
        self.scroll_count = 0
        self.refresh_count = 0
        self.error_count = 0

    async def navigate(self, url: str | None = None) -> None:
        """Navigate to URL (or to the stored url)."""
        target = url or self.url
        if self.page is None:
            self.page = await self.context.new_page()
        try:
            await self.page.goto(target, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1)
        except Exception as e:
            self.error_count += 1
            logger.warning("Tab %s navigate failed: %s", self.tab_id, e)

    async def get_page_height(self) -> int:
        if self.page is None:
            return 0
        try:
            return await self.page.evaluate(
                "(() => { const el = document.querySelector('.scrollbar') || document.documentElement; return el.scrollHeight; })()"
            )
        except Exception:
            return 0

    async def get_scroll_y(self) -> int:
        if self.page is None:
            return 0
        try:
            return await self.page.evaluate(
                "(() => { const el = document.querySelector('.scrollbar') || document.documentElement; return el.scrollTop; })()"
            )
        except Exception:
            return 0

    async def scroll_by(self, delta: int, duration_ms: float = 500) -> None:
        """Scroll by delta px (APK's V2.r.h() method).

        Uses the site's scrollable container when present (yo.fan content
        lives in a ``DIV.scrollbar``), otherwise falls back to window.
        """
        if self.page is None:
            return
        try:
            await self.page.evaluate(
                f"(() => {{ const el = document.querySelector('.scrollbar') || document.documentElement; el.scrollBy({{top: {delta}, left: 0, behavior: 'smooth'}}); }})()"
            )
            await asyncio.sleep(duration_ms / 1000)
            self.scroll_count += 1
        except Exception as e:
            self.error_count += 1
            logger.debug("Scroll failed: %s", e)

    async def scroll_to(self, y: int, duration_ms: float = 500) -> None:
        if self.page is None:
            return
        try:
            await self.page.evaluate(
                f"(() => {{ const el = document.querySelector('.scrollbar') || document.documentElement; el.scrollTo({{top: {y}, left: 0, behavior: 'smooth'}}); }})()"
            )
            await asyncio.sleep(duration_ms / 1000)
        except Exception:
            pass

    async def clear_storage(self) -> None:
        """Clear browser storage (APK's V2.r.b() — localStorage, sessionStorage, indexedDB)."""
        if self.page is None:
            return
        try:
            await self.page.evaluate("""
                try { sessionStorage.clear(); } catch(e) {}
                try { localStorage.clear(); } catch(e) {}
                try {
                    indexedDB.databases().then(dbs =>
                        dbs.forEach(db => indexedDB.deleteDatabase(db.name))
                    );
                } catch(e) {}
            """)
        except Exception:
            pass

    async def refresh(self) -> None:
        """Reload the page."""
        if self.page is None:
            return
        try:
            await self.clear_storage()
            await self.page.reload(wait_until="domcontentloaded", timeout=30000)
            self.refresh_count += 1
            await asyncio.sleep(1)
        except Exception as e:
            self.error_count += 1
            logger.warning("Refresh failed: %s", e)

    async def evaluate(self, js: str) -> Any:
        if self.page is None:
            return None
        try:
            return await self.page.evaluate(js)
        except Exception:
            return None

    async def close(self) -> None:
        try:
            await self.clear_storage()
            await self.context.close()
        except Exception:
            pass


class TabManager:
    """Manages all tabs (contexts) for a session (APK's U2.c)."""

    def __init__(self) -> None:
        self._tabs: dict[str, Tab] = {}
        self._next_index = 0

    async def create_tab(
        self,
        context: Any,
        url: str,
        proxy_url: str | None = None,
    ) -> Tab:
        tab_id = f"tab_{self._next_index}"
        tab = Tab(context, tab_id, self._next_index, url)
        self._tabs[tab_id] = tab
        self._next_index += 1
        return tab

    def get(self, tab_id: str) -> Tab | None:
        return self._tabs.get(tab_id)

    def all(self) -> list[Tab]:
        return list(self._tabs.values())

    def count(self) -> int:
        return len(self._tabs)

    async def remove(self, tab_id: str) -> None:
        tab = self._tabs.pop(tab_id, None)
        if tab is not None:
            await tab.close()

    async def remove_all(self) -> None:
        for tab in list(self._tabs.values()):
            await tab.close()
        self._tabs.clear()