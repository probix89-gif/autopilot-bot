"""Application entry point."""

import asyncio
import logging

from autopilot.bot.dispatcher import build_app
from autopilot.config import get_settings
from autopilot.health import HealthServer
from autopilot.utils.logging import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    setup_logging()

    if not settings.BOT_TOKEN:
        logger.error("BOT_TOKEN not set")
        raise SystemExit(1)
    if not settings.is_admin:
        logger.error("ADMIN_USER_IDS not set")
        raise SystemExit(1)

    logger.info("AutoPilot Bot starting…")

    port = int(settings.HEALTH_PORT)
    health = HealthServer(port=port)
    await health.start()

    try:
        app = await build_app(settings)
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=["message", "callback_query"])
        logger.info("Online. Ctrl+C to stop.")
    except Exception:
        logger.exception("Failed to start bot")
        await health.stop()
        raise

    try:
        await app.updater.idle()
    finally:
        await app.shutdown()
        container = app.bot_data.get("container")
        if container is not None:
            await container.teardown()
        await health.stop()


if __name__ == "__main__":
    asyncio.run(main())