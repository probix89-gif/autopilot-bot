"""Session scheduler — one session = one target URL with N tabs.

Faithful to the APK: a session starts with `tab_count` tabs, each tab
gets a unique fingerprint profile + optional proxy + stealth injection,
then the automator loop runs per tab. Sessions support pause/resume,
add_tab/remove_tab, and per-session statistics.
"""

import asyncio
import logging
import random

from autopilot.domain.enums import AutomationMode, SessionStatus
from autopilot.domain.schemas import AutomationConfig
from autopilot.engine.automator import Automator
from autopilot.engine.browser import BrowserManager
from autopilot.engine.fingerprint import ProfileDatabase
from autopilot.engine.proxy_manager import ProxyManager
from autopilot.engine.stealth import StealthInjector
from autopilot.engine.tab_manager import Tab, TabManager

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


class SessionRunner:
    """Owns one session's lifecycle: contexts → automators → cleanup."""

    def __init__(
        self,
        session_id: str,
        url: str,
        config: AutomationConfig,
        browser: BrowserManager,
        proxy_mgr: ProxyManager,
        profile_db: ProfileDatabase,
        stealth: StealthInjector,
        stats_callback=None,
        headless: bool = True,
    ) -> None:
        self.session_id = session_id
        self.url = url
        self.config = config
        self.browser = browser
        self.proxy_mgr = proxy_mgr
        self.profile_db = profile_db
        self.stealth = stealth
        self.stats_callback = stats_callback
        self.headless = headless

        self.tab_manager = TabManager()
        self.automators: dict[str, Automator] = {}
        self._tasks: list[asyncio.Task] = []
        self._paused = asyncio.Event()
        self._paused.set()

    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Create tabs and kick off automation."""
        await self.browser.ensure_started()

        proxies = []
        if self.config.enable_proxy:
            proxies = await self.proxy_mgr.get_many(self.config.tab_count)
            if len(proxies) < self.config.tab_count:
                logger.warning("Only %d proxies for %d tabs", len(proxies), self.config.tab_count)

        for i in range(self.config.tab_count):
            await self._create_tab(i, proxies[i].url if i < len(proxies) else None)

        logger.info(
            "Session %s started: %d tabs → %s (mode=%s)",
            self.session_id,
            self.tab_manager.count(),
            self.url,
            self.config.mode.value,
        )

    async def _create_tab(self, index: int, proxy_url: str | None) -> None:
        """Create one tab: profile → stealth → context → navigate → automator."""
        fp = self.profile_db.get_or_create(f"tab_{index}")

        # Build a Playwright context
        ctx = await self.browser.new_context(
            proxy_url=proxy_url,
            user_agent=fp.user_agent,
            timezone_id=fp.timezone,
            viewport={"width": fp.screen_width, "height": fp.screen_height},
        )

        # Apply stealth injection (APK's W2.b)
        if self.config.enable_spoofing:
            await self.stealth.apply(ctx, fp)

        tab = await self.tab_manager.create_tab(ctx, self.url, proxy_url)
        await tab.navigate(self.url)

        # Start per-tab automator
        automator = Automator(
            tab=tab,
            mode=self.config.mode,
            scroll_interval=self.config.scroll_interval_sec,
            refresh_interval=self.config.refresh_interval_sec,
            custom_js=self.config.custom_js,
            randomize=self.config.randomize_intervals,
            stats_callback=self.stats_callback,
        )
        self.automators[tab.tab_id] = automator
        task = asyncio.create_task(self._run_automator(automator, tab))
        self._tasks.append(task)

    async def _run_automator(self, automator: Automator, tab: Tab) -> None:
        try:
            while True:
                await self._paused.wait()
                if automator._stop.is_set():
                    break
                await automator.run()
                if automator._stop.is_set():
                    break
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Tab %s automation crashed", tab.tab_id)

    async def pause(self) -> None:
        self._paused.clear()
        for a in self.automators.values():
            a._stop.set()
        logger.info("Session %s paused", self.session_id)

    async def resume(self) -> None:
        self._paused.set()
        # Reset automators so they can loop again
        for a in self.automators.values():
            a._stop.clear()
        logger.info("Session %s resumed", self.session_id)

    async def add_tab(self) -> Tab | None:
        """Add one more tab (ACTION_ADD_TAB)."""
        if self.tab_manager.count() >= 8:
            return None
        proxies = []
        if self.config.enable_proxy:
            proxies = await self.proxy_mgr.get_many(1)
        proxy_url = proxies[0].url if proxies else None
        idx = self.tab_manager.count()
        await self._create_tab(idx, proxy_url)
        return self.tab_manager.get(f"tab_{idx}")

    async def remove_tab(self, tab_id: str) -> bool:
        """Remove a specific tab (TabManager.c())."""
        automator = self.automators.pop(tab_id, None)
        if automator is not None:
            await automator.stop()
        await self.tab_manager.remove(tab_id)
        return True

    async def stop(self) -> None:
        """Stop all automators and close all tabs."""
        for a in self.automators.values():
            await a.stop()
        for task in self._tasks:
            if not task.done():
                task.cancel()
        for task in self._tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()
        await self.tab_manager.remove_all()
        self.automators.clear()
        logger.info("Session %s stopped", self.session_id)

    @property
    def is_running(self) -> bool:
        return len(self._tasks) > 0 and any(not t.done() for t in self._tasks)


class SessionScheduler:
    """Registry of active session runners."""

    def __init__(
        self,
        browser: BrowserManager,
        proxy_mgr: ProxyManager,
        profile_db: ProfileDatabase,
        stealth: StealthInjector,
        stats_callback=None,
        headless: bool = True,
    ) -> None:
        self.browser = browser
        self.proxy_mgr = proxy_mgr
        self.profile_db = profile_db
        self.stealth = stealth
        self.stats_callback = stats_callback
        self.headless = headless
        self._runners: dict[str, SessionRunner] = {}

    async def create_runner(
        self, session_id: str, url: str, config: AutomationConfig
    ) -> SessionRunner:
        runner = SessionRunner(
            session_id=session_id,
            url=url,
            config=config,
            browser=self.browser,
            proxy_mgr=self.proxy_mgr,
            profile_db=self.profile_db,
            stealth=self.stealth,
            stats_callback=self.stats_callback,
            headless=self.headless,
        )
        self._runners[session_id] = runner
        return runner

    async def start_session(self, session_id: str) -> None:
        runner = self._runners.get(session_id)
        if runner is None:
            raise ValueError(f"Runner not found: {session_id}")
        await runner.start()

    async def pause_session(self, session_id: str) -> None:
        runner = self._runners.get(session_id)
        if runner is not None:
            await runner.pause()

    async def resume_session(self, session_id: str) -> None:
        runner = self._runners.get(session_id)
        if runner is not None:
            await runner.resume()

    async def stop_session(self, session_id: str) -> None:
        runner = self._runners.get(session_id)
        if runner is not None:
            await runner.stop()
            self._runners.pop(session_id, None)

    async def get_runner(self, session_id: str) -> SessionRunner | None:
        return self._runners.get(session_id)

    def runner_count(self) -> int:
        return len(self._runners)