"""Core automation engine — APK-faithful 4 modes with human-like behavior.

Ports the APK's T2.A methods d (deep scroll), e (simple scroll), and
the refresh cycle logic (method b). Each mode runs as an asyncio task
that controls a single tab and faithfully reproduces the APK's random
timing, reading pauses, scroll-back corrections, distraction pauses,
and storage-clearing refresh cycles.
"""

import asyncio
import logging
import random
import time

from autopilot.domain.enums import AutomationMode
from autopilot.engine.tab_manager import Tab

logger = logging.getLogger(__name__)

# APK-faithful random helpers
def _gauss(mean: float, dev: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, random.gauss(mean, dev)))


def _chance(pct: int) -> bool:
    return random.randint(1, 100) <= pct


def _randint(a: int, b: int) -> int:
    return random.randint(a, b)


class Automator:
    """Runs automation on a single tab (APK's T2.A per-tab loop)."""

    def __init__(
        self,
        tab: Tab,
        mode: AutomationMode,
        scroll_interval: int = 10,
        refresh_interval: int = 30,
        custom_js: str = "",
        randomize: bool = True,
        stats_callback=None,
    ) -> None:
        self.tab = tab
        self.mode = mode
        self.scroll_interval = scroll_interval  # seconds
        self.refresh_interval = refresh_interval  # seconds
        self.custom_js = custom_js
        self.randomize = randomize
        self.stats_callback = stats_callback
        self._stop = asyncio.Event()

    async def run(self) -> None:
        """Start the automation loop for the configured mode."""
        runner = {
            AutomationMode.SIMPLE_SCROLL: self._simple_scroll,
            AutomationMode.DEEP_SCROLL: self._deep_scroll,
            AutomationMode.TAB_SWITCHING: self._tab_switching,
            AutomationMode.CUSTOM_JS: self._custom_js,
        }.get(self.mode)
        if runner is None:
            logger.error("Unknown mode: %s", self.mode)
            return
        logger.info("Tab %s starting %s", self.tab.tab_id, self.mode.value)
        await runner()

    async def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------
    # APK method b: refresh cycle calculation
    # refresh_interval / scroll_interval = scrolls per refresh
    # ------------------------------------------------------------------
    def _scrolls_per_refresh(self) -> int:
        ratio = self.refresh_interval // self.scroll_interval
        if ratio < 1:
            ratio = 1
        if self.randomize:
            lo = max(2, ratio - 2)
            hi = ratio + 2
            return random.randint(lo, hi)
        return ratio

    # ------------------------------------------------------------------
    # SIMPLE_SCROLL — APK method e (faithful)
    # Scroll → reading pause → 15% scroll-back → 5% distraction → small pause
    # ------------------------------------------------------------------
    async def _simple_scroll(self) -> None:
        scrolls = 0
        scrolls_per_refresh = self._scrolls_per_refresh()

        while not self._stop.is_set():
            # 1. Random scroll distance (APK: Y2.a.d() = ~viewport height * random)
            viewport_h = await self.tab.get_page_height()
            if viewport_h < 100:
                viewport_h = 720
            scroll_by = _randint(200, max(300, viewport_h // 2))
            dur = _gauss(500, 150, 200, 1000)
            await self.tab.scroll_by(scroll_by, dur)
            scrolls += 1
            await self._track("scrolls_performed")

            # 2. Reading pause (APK: randomized = scrollInterval*1000, else 5-12s)
            if self.randomize:
                pause = self.scroll_interval * 1000
            else:
                pause = _gauss(5000, 2000, 2000, 12000)
            await self._event("ReadingPause", f"{int(pause/1000)}s")
            await self._sleep(pause / 1000)

            # 3. 15% chance: scroll-back correction (APK: e method)
            if _chance(15):
                back = -(scroll_by // _randint(2, 5))
                dur2 = _gauss(500, 150, 200, 1000)
                await self.tab.scroll_by(back, dur2)
                await self._event("ScrollPerformed", f"{abs(back)}px up")
                await self._sleep(_gauss(1500, 400, 500, 4000) / 1000)

            # 4. 5% chance: distraction pause (APK: 4-25s)
            if _chance(5):
                dist_pause = _gauss(10000, 4000, 4000, 25000)
                await self._event("DistractionPause", f"{int(dist_pause/1000)}s")
                await self._sleep(dist_pause / 1000)

            # 5. Small pause (APK: 150-1000ms)
            await self._sleep(_gauss(400, 150, 150, 1000) / 1000)

            # 6. Refresh cycle (APK: every N scrolls, clear storage, reload)
            if scrolls >= scrolls_per_refresh:
                await self._event("RefreshTriggered", f"after {scrolls} scrolls")
                await self.tab.clear_storage()
                await self.tab.refresh()
                scrolls = 0
                scrolls_per_refresh = self._scrolls_per_refresh()

    # ------------------------------------------------------------------
    # DEEP_SCROLL — APK method d (faithful)
    # 1-3 viewport scrolls → overshoot → scroll to top → refresh
    # ------------------------------------------------------------------
    async def _deep_scroll(self) -> None:
        scrolls = 0
        scrolls_per_refresh = self._scrolls_per_refresh()

        while not self._stop.is_set():
            page_h = await self.tab.get_page_height()
            if page_h < 100:
                page_h = 720
            scroll_y = await self.tab.get_scroll_y()

            # 1. Scroll 1-3 viewport heights (APK: Y2.a.d() * random(1,3))
            if scroll_y < page_h - 1000:
                chunk = random.randint(1, 3) * min(page_h, 720)
                dur = _gauss(500, 150, 200, 1000)
                await self.tab.scroll_by(chunk, dur)
                scrolls += 1
                await self._track("scrolls_performed")

                # 2. Overshoot correction (10% chance — APK: d method)
                if _chance(10):
                    await self.tab.scroll_by(-200, 200)
                    await self._sleep(_gauss(400, 150, 150, 1000) / 1000)
                    await self.tab.scroll_by(-150, 300)
                    await self._event("OvershootCorrected", "200px back")
                    await self._sleep(_gauss(1500, 400, 500, 4000) / 1000)

                # 3. Reading pause (APK: 2-12s)
                pause = _gauss(5000, 2000, 2000, 12000)
                await self._event("ReadingPause", f"{int(pause/1000)}s")
                await self._sleep(pause / 1000)

            else:
                # 4. Reached bottom: scroll to top in chunks (APK: d method)
                await self._event("ScrollToTop", "bottom reached")
                chunk = _randint(2, 4) * min(page_h, 720)
                rem = scroll_y
                while rem > 0 and not self._stop.is_set():
                    step = min(rem, chunk)
                    await self.tab.scroll_by(-step, _gauss(500, 150, 200, 1000))
                    rem -= step
                    await self._sleep(_gauss(400, 150, 150, 1000) / 1000)
                scrolls = 0
                scrolls_per_refresh = self._scrolls_per_refresh()

            # 5. Refresh
            if scrolls >= scrolls_per_refresh:
                await self._event("RefreshTriggered", f"after {scrolls} scrolls")
                await self.tab.clear_storage()
                await self.tab.refresh()
                scrolls = 0
                scrolls_per_refresh = self._scrolls_per_refresh()

    # ------------------------------------------------------------------
    # TAB_SWITCHING — rotate through tabs
    # ------------------------------------------------------------------
    async def _tab_switching(self) -> None:
        while not self._stop.is_set():
            modes = [AutomationMode.SIMPLE_SCROLL, AutomationMode.DEEP_SCROLL]
            mode = random.choice(modes)
            await self._event("TabSwitch", f"switching to {mode.value}")
            scroll = _randint(200, 700)
            await self.tab.scroll_by(scroll, _gauss(500, 150, 200, 1000))
            await self._track("tabs_switched")
            await self._sleep(random.randint(30, 90))

    # ------------------------------------------------------------------
    # CUSTOM_JS — inject user script at intervals
    # ------------------------------------------------------------------
    async def _custom_js(self) -> None:
        if not self.custom_js:
            logger.warning("CUSTOM_JS mode but no script provided")
            return
        while not self._stop.is_set():
            await self.tab.evaluate(self.custom_js)
            await self._track("js_executions")
            await self._sleep(self.scroll_interval)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _sleep(self, secs: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=max(0.1, secs))
            return True
        except asyncio.TimeoutError:
            return False

    async def _event(self, event_type: str, detail: str = "") -> None:
        logger.debug("Tab %s | %s %s", self.tab.tab_id, event_type, detail)

    async def _track(self, field: str) -> None:
        if self.stats_callback is not None:
            try:
                await self.stats_callback(field)
            except Exception:
                pass