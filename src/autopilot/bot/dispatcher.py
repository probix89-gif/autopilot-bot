"""Telegram bot dispatcher."""

import logging

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, ContextTypes

from autopilot.bot.commands import register as register_commands
from autopilot.container import Container
from autopilot.engine.scheduler import SessionScheduler

logger = logging.getLogger(__name__)


def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error: %s", context.error)


async def build_app(settings) -> Application:
    """Build the fully-wired Telegram bot Application."""
    container = Container(settings)
    await container.setup()

    # Scheduler
    scheduler = SessionScheduler(
        browser=container.browser,
        proxy_mgr=container.proxy_mgr,
        profile_db=container.profile_db,
        stealth=container.stealth,
        headless=True,
    )

    app = (
        ApplicationBuilder()
        .token(settings.BOT_TOKEN)
        .build()
    )

    app.bot_data["container"] = container
    app.bot_data["db"] = container.db
    app.bot_data["session_repo"] = container.session_repo
    app.bot_data["stats_repo"] = container.stats_repo
    app.bot_data["proxy_repo"] = container.proxy_repo
    app.bot_data["proxy_manager"] = container.proxy_mgr
    app.bot_data["browser"] = container.browser
    app.bot_data["profile_db"] = container.profile_db
    app.bot_data["stealth"] = container.stealth
    app.bot_data["scheduler"] = scheduler

    register_commands(app)
    app.add_error_handler(error_handler)

    logger.info("Bot built: %d admins, %d proxy sources",
                len(settings.ADMIN_USER_IDS), len(settings.PROXY_SOURCES))
    return app