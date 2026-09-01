"""Playwright browser lifecycle (lazy-started on first session)."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BrowserManager:
    """Owns the single Chromium instance."""

    def __init__(self, headless: bool = True) -> None:
        self.headless = headless
        self._playwright: Any = None
        self._browser: Any = None
        self._contexts: list = []

    async def start(self) -> None:
        if self._browser is not None:
            return
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        logger.info("Chromium launched (headless=%s)", self.headless)

    async def ensure_started(self) -> None:
        if self._browser is None:
            await self.start()

    async def new_context(
        self,
        proxy_url: str | None = None,
        user_agent: str | None = None,
        timezone_id: str | None = None,
        viewport: dict | None = None,
        apply_init=None,
    ) -> Any:
        if self._browser is None:
            raise RuntimeError("Browser not started. Call start()/ensure_started().")

        options: dict = {}
        if proxy_url:
            options["proxy"] = {"server": proxy_url}
        if user_agent:
            options["user_agent"] = user_agent
        if timezone_id:
            options["timezone_id"] = timezone_id
        if viewport:
            options["viewport"] = viewport

        context = await self._browser.new_context(**options)
        if apply_init is not None:
            await apply_init(context)
        self._contexts.append(context)
        return context

    async def close_context(self, context) -> None:
        try:
            if context in self._contexts:
                self._contexts.remove(context)
            await context.close()
        except Exception:
            logger.exception("Failed to close context")

    async def screenshot(self, context, path: str) -> str | None:
        try:
            pages = context.pages
            if not pages:
                return None
            await pages[0].screenshot(path=path)
            return path
        except Exception:
            logger.exception("Screenshot failed")
            return None

    async def stop(self) -> None:
        for ctx in list(self._contexts):
            try:
                await ctx.close()
            except Exception:
                pass
        self._contexts.clear()
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        logger.info("Browser stopped")