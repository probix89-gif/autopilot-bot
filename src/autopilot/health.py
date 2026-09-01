"""Minimal health HTTP server for Railway."""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_STATUS_LINE = b"HTTP/1.1 200 OK\r\n"
_HEADERS = (
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 2\r\n"
    b"Connection: close\r\n"
    b"\r\n"
)
_BODY = b"OK"


class HealthServer:
    def __init__(self, port: int = 8080, host: str = "0.0.0.0") -> None:
        self.port = port
        self.host = host
        self._server: Any = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            try:
                await asyncio.wait_for(reader.read(8192), timeout=3)
            except (asyncio.TimeoutError, ConnectionError):
                pass
            writer.write(_STATUS_LINE + _HEADERS + _BODY)
            await writer.drain()
        except (ConnectionError, BrokenPipeError):
            pass
        except Exception:
            logger.debug("Health error", exc_info=True)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, host=self.host, port=self.port)
        logger.info("Health server on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None