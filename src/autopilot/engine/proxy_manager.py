"""Proxy pool manager — fetch, validate, rotate (APK-faithful sources)."""

import asyncio
import logging
import random
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

GEONODE_URL = (
    "https://proxylist.geonode.com/api/proxy-list?limit=50&page=1"
    "&sort_by=lastChecked&sort_type=desc&protocols=http%2Chttps"
)
PROXYSCRAPE_URL = (
    "https://api.proxyscrape.com/v2/?request=displayproxies"
    "&protocol=http&timeout=5000&country=all&ssl=yes&anonymity=all"
)
IP_CHECK_URL = "https://api.myip.com"


@dataclass
class ProxyEntry:
    url: str
    protocol: str = "http"
    country: str | None = None
    is_active: bool = False
    latency_ms: int | None = None
    fail_count: int = 0


class ProxyManager:
    def __init__(self, sources=None, custom_proxies=None, min_pool=5, max_pool=100):
        self.sources = sources or ["geonode", "proxyscrape"]
        self.custom_proxies = custom_proxies or []
        self.min_pool = min_pool
        self.max_pool = max_pool
        self._pool: list[ProxyEntry] = []
        self._lock = asyncio.Lock()

    async def refresh(self) -> int:
        raw: list[ProxyEntry] = []
        async with self._lock:
            for source in self.sources:
                try:
                    if source == "geonode":
                        raw.extend(await self._fetch_geonode())
                    elif source == "proxyscrape":
                        raw.extend(await self._fetch_proxyscrape())
                    elif source == "custom":
                        raw.extend(self._parse_custom(self.custom_proxies))
                except Exception:
                    logger.exception("Proxy source %s failed", source)

            seen: set[str] = set()
            deduped = []
            for p in raw:
                if p.url not in seen:
                    seen.add(p.url)
                    deduped.append(p)

            self._pool = await self._validate_many(deduped[: self.max_pool])
            logger.info("Proxy refresh: %d raw → %d active", len(deduped), len(self._pool))
        return len(self._pool)

    async def get_many(self, count: int) -> list[ProxyEntry]:
        async with self._lock:
            if not self._pool:
                return []
            return random.sample(self._pool, min(count, len(self._pool)))

    async def mark_bad(self, url: str) -> None:
        async with self._lock:
            for p in self._pool:
                if p.url == url:
                    p.fail_count += 1
                    if p.fail_count >= 3:
                        p.is_active = False
                    return

    @property
    def pool_size(self) -> int:
        return len(self._pool)

    # ---- sources ----
    async def _fetch_geonode(self) -> list[ProxyEntry]:
        entries = []
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(GEONODE_URL)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("data", []):
                host, port = item.get("ip"), item.get("port")
                if not host or not port:
                    continue
                country = (item.get("country") or "").upper()[:2] or None
                entries.append(ProxyEntry(url=f"http://{host}:{port}", protocol="http", country=country))
        return entries

    async def _fetch_proxyscrape(self) -> list[ProxyEntry]:
        entries = []
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(PROXYSCRAPE_URL)
            resp.raise_for_status()
            for line in resp.text.splitlines():
                line = line.strip()
                if line:
                    entries.append(ProxyEntry(url=f"http://{line}", protocol="http"))
        return entries

    def _parse_custom(self, raw_list) -> list[ProxyEntry]:
        entries = []
        for item in raw_list:
            item = item.strip()
            if not item:
                continue
            url = item if "://" in item else f"http://{item}"
            proto = url.split("://", 1)[0]
            entries.append(ProxyEntry(url=url, protocol=proto))
        return entries

    # ---- validation ----
    async def _validate_many(self, proxies: list[ProxyEntry]) -> list[ProxyEntry]:
        sem = asyncio.Semaphore(20)

        async def check(p: ProxyEntry) -> ProxyEntry | None:
            async with sem:
                try:
                    async with httpx.AsyncClient(timeout=8, proxy=p.url, verify=False) as client:
                        start = asyncio.get_event_loop().time()
                        resp = await client.get(IP_CHECK_URL)
                        latency = int((asyncio.get_event_loop().time() - start) * 1000)
                        if resp.status_code == 200:
                            p.is_active = True
                            p.latency_ms = latency
                            return p
                except Exception:
                    pass
                return None

        results = await asyncio.gather(*(check(p) for p in proxies))
        return [p for p in results if p is not None]