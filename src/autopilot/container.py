"""Shared FastAPI-free app dependencies (DB, engine services)."""

from autopilot.database import Database
from autopilot.engine.browser import BrowserManager
from autopilot.engine.fingerprint import ProfileDatabase
from autopilot.engine.proxy_manager import ProxyManager
from autopilot.engine.stealth import StealthInjector
from autopilot.models import SessionRepo, StatsRepo, ProxyRepo, UserRepo


class Container:
    """Wires all services together once at boot."""

    def __init__(self, settings) -> None:
        self.settings = settings
        self.db = Database(settings.DB_PATH)
        self.session_repo = SessionRepo(self.db)
        self.stats_repo = StatsRepo(self.db)
        self.proxy_repo = ProxyRepo(self.db)
        self.user_repo = UserRepo(self.db)
        self.proxy_mgr = ProxyManager(
            sources=settings.PROXY_SOURCES,
            custom_proxies=settings.CUSTOM_PROXIES,
        )
        self.browser = BrowserManager(headless=True)
        self.profile_db = ProfileDatabase()
        self.stealth = StealthInjector()

    async def setup(self) -> None:
        await self.db.connect()

    async def teardown(self) -> None:
        await self.browser.stop()
        await self.db.close()