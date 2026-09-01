"""All Telegram command handlers — APK-faithful session management.

Commands:
  /add <url> — New session targeting a URL (e.g. /add https://yo.fan/p/abc123)
  /list / /sessions — List all sessions
  /start <id> — Start automation
  /pause <id> — Pause session
  /resume <id> — Resume session
  /stop <id> — Stop session
  /delete <id> — Delete session
  /tabs <id> — List tabs for a session
  /add_tab <id> — Add a tab to running session
  /remove_tab <id> <tab_index> — Remove a tab
  /config <id> — View session config
  /config <id> key=value — Update config (e.g. /config abc123 tabs=5)
  /stats <id> — Session statistics
  /screenshot <id> — Screenshot
  /events <id> — Recent automation events
  /proxies — Proxy pool status
  /refresh_proxies — Force proxy refresh
  /help — Full help
  /start — Welcome
"""

import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from autopilot.config import get_settings
from autopilot.domain.enums import AutomationMode, SessionStatus
from autopilot.domain.schemas import AutomationConfig
from autopilot.engine.scheduler import SessionScheduler

logger = logging.getLogger(__name__)

ALLOWED = filters.ChatType.PRIVATE & filters.User(user_id=get_settings().ADMIN_USER_IDS)


def _session_text(s: dict) -> str:
    """Format session for telegram."""
    return (
        f"`{s['id']}`  **{s.get('name', '') or 'Unnamed'}**\n"
        f"URL: {s.get('url', 'N/A')[:60]}\n"
        f"Status: `{s['status']}`  Mode: `{s['mode']}`\n"
        f"Tabs: {s['tab_count']}  Proxy: {'✅' if s['enable_proxy'] else '❌'}  "
        f"Spoof: {'✅' if s['enable_spoofing'] else '❌'}"
    )


# ------------------------------------------------------------------
# /start
# ------------------------------------------------------------------
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 *AutoPilot Bot*\n\n"
        "Generate views on your content pages with anti-detection automation.\n\n"
        "Commands:\n"
        "`/add <url>` — New session for a URL\n"
        "`/list` — All sessions\n"
        "`/help` — Full command list",
        parse_mode=ParseMode.MARKDOWN,
    )


# ------------------------------------------------------------------
# /add <url> — New session
# ------------------------------------------------------------------
async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text(
            "Usage: `/add <url>`\nExample: `/add https://yo.fan/p/pb8nDtbKsfe`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    url = " ".join(ctx.args).strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    repo = ctx.bot_data.get("session_repo")
    scheduler = ctx.bot_data.get("scheduler")
    if repo is None:
        await update.message.reply_text("❌ Database not available")
        return

    # Default config matches APK defaults: 5 tabs, refresh 30s, scroll 10s, randomize on
    config = AutomationConfig(
        mode=AutomationMode.SIMPLE_SCROLL,
        tab_count=5,
        refresh_interval_sec=30,
        scroll_interval_sec=10,
        enable_proxy=False,
        enable_spoofing=False,
        randomize_intervals=True,
    )
    result = await repo.create(url, "", config)
    if scheduler is not None:
        await scheduler.create_runner(result["id"], url, config)

    await update.message.reply_text(
        f"✅ Session created for URL:\n`{url}`\n\n"
        f"Session ID: `{result['id']}`\n"
        f"Tabs: {config.tab_count}  |  Mode: {config.mode.value}\n\n"
        f"Use `/start {result['id']}` to begin automation.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ------------------------------------------------------------------
# /list / /sessions
# ------------------------------------------------------------------
async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    repo = ctx.bot_data.get("session_repo")
    if repo is None:
        return
    rows = await repo.list()
    if not rows:
        await update.message.reply_text("No sessions. Use `/add <url>` to create one.",
                                        parse_mode=ParseMode.MARKDOWN)
        return
    for r in rows:
        text = _session_text(r)
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    await update.message.reply_text(f"Total: {len(rows)} sessions")


# ------------------------------------------------------------------
# /start <id>
# ------------------------------------------------------------------
async def cmd_start_session(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text("Usage: `/start <session_id>`", parse_mode=ParseMode.MARKDOWN)
        return
    sid = ctx.args[0]
    scheduler = ctx.bot_data.get("scheduler")
    repo = ctx.bot_data.get("session_repo")
    if scheduler is None:
        await update.message.reply_text("❌ Scheduler not available")
        return
    try:
        await scheduler.start_session(sid)
        if repo:
            await repo.update_status(sid, SessionStatus.RUNNING.value)
        await update.message.reply_text(f"▶ Started: `{sid}`", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ Failed: {e}")


# ------------------------------------------------------------------
# /pause <id>
# ------------------------------------------------------------------
async def cmd_pause(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        return
    sid = ctx.args[0]
    scheduler = ctx.bot_data.get("scheduler")
    if scheduler:
        await scheduler.pause_session(sid)
    await update.message.reply_text(f"⏸ Paused: `{sid}`", parse_mode=ParseMode.MARKDOWN)


# ------------------------------------------------------------------
# /resume <id>
# ------------------------------------------------------------------
async def cmd_resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        return
    sid = ctx.args[0]
    scheduler = ctx.bot_data.get("scheduler")
    if scheduler:
        await scheduler.resume_session(sid)
    await update.message.reply_text(f"▶ Resumed: `{sid}`", parse_mode=ParseMode.MARKDOWN)


# ------------------------------------------------------------------
# /stop <id>
# ------------------------------------------------------------------
async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        return
    sid = ctx.args[0]
    scheduler = ctx.bot_data.get("scheduler")
    repo = ctx.bot_data.get("session_repo")
    if scheduler:
        await scheduler.stop_session(sid)
    if repo:
        await repo.update_status(sid, SessionStatus.STOPPED.value)
    await update.message.reply_text(f"⏹ Stopped: `{sid}`", parse_mode=ParseMode.MARKDOWN)


# ------------------------------------------------------------------
# /delete <id>
# ------------------------------------------------------------------
async def cmd_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        return
    sid = ctx.args[0]
    scheduler = ctx.bot_data.get("scheduler")
    repo = ctx.bot_data.get("session_repo")
    if scheduler:
        await scheduler.stop_session(sid)
    if repo:
        await repo.delete(sid)
    await update.message.reply_text(f"❌ Deleted: `{sid}`", parse_mode=ParseMode.MARKDOWN)


# ------------------------------------------------------------------
# /tabs <id>
# ------------------------------------------------------------------
async def cmd_tabs(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        return
    sid = ctx.args[0]
    scheduler = ctx.bot_data.get("scheduler")
    if scheduler is None:
        return
    runner = await scheduler.get_runner(sid)
    if runner is None:
        await update.message.reply_text(f"Session `{sid}` has no active tabs", parse_mode=ParseMode.MARKDOWN)
        return
    tabs = runner.tab_manager.all()
    if not tabs:
        await update.message.reply_text("No tabs")
        return
    lines = [f"Tabs for `{sid}` ({len(tabs)} active):"]
    for t in tabs:
        lines.append(f"  `{t.tab_id}` idx={t.index}  scrolls={t.scroll_count}  errors={t.error_count}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ------------------------------------------------------------------
# /add_tab <id>
# ------------------------------------------------------------------
async def cmd_add_tab(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        return
    sid = ctx.args[0]
    scheduler = ctx.bot_data.get("scheduler")
    if scheduler is None:
        return
    runner = await scheduler.get_runner(sid)
    if runner is None:
        await update.message.reply_text("Session not running")
        return
    tab = await runner.add_tab()
    if tab:
        await update.message.reply_text(f"➕ Tab added: `{tab.tab_id}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("Max tabs reached (8)")


# ------------------------------------------------------------------
# /remove_tab <id> <tab_index>
# ------------------------------------------------------------------
async def cmd_remove_tab(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if len(ctx.args) < 2:
        return
    sid, idx = ctx.args[0], ctx.args[1]
    scheduler = ctx.bot_data.get("scheduler")
    if scheduler is None:
        return
    runner = await scheduler.get_runner(sid)
    if runner is None:
        return
    tab_id = f"tab_{idx}"
    ok = await runner.remove_tab(tab_id)
    await update.message.reply_text(f"➖ Removed tab `{tab_id}`" if ok else "Tab not found",
                                    parse_mode=ParseMode.MARKDOWN)


# ------------------------------------------------------------------
# /config <id> [key=value]
# ------------------------------------------------------------------
async def cmd_config(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        return
    sid = ctx.args[0]
    repo = ctx.bot_data.get("session_repo")
    if repo is None:
        return
    row = await repo.get(sid)
    if row is None:
        await update.message.reply_text("Session not found")
        return

    # If no extra args, show current config
    if len(ctx.args) == 1:
        text = (
            f"⚙ Config for `{sid}`\n\n"
            f"Mode: `{row['mode']}`\n"
            f"Tabs: {row['tab_count']}\n"
            f"Refresh: {row['refresh_interval_sec']}s\n"
            f"Scroll: {row['scroll_interval_sec']}s\n"
            f"Proxy: {'✅' if row['enable_proxy'] else '❌'}\n"
            f"Spoof: {'✅' if row['enable_spoofing'] else '❌'}\n"
            f"Randomize: {'✅' if row['randomize_intervals'] else '❌'}\n"
            f"URL: {row.get('url', 'N/A')[:60]}"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    # Update config: key=value
    keyval = " ".join(ctx.args[1:])
    if "=" not in keyval:
        return
    key, val = keyval.split("=", 1)
    key = key.strip().lower()
    val = val.strip()

    config = AutomationConfig(
        mode=row["mode"],
        tab_count=row["tab_count"],
        refresh_interval_sec=row["refresh_interval_sec"],
        scroll_interval_sec=row["scroll_interval_sec"],
        enable_proxy=bool(row["enable_proxy"]),
        enable_spoofing=bool(row["enable_spoofing"]),
        randomize_intervals=bool(row["randomize_intervals"]),
        custom_js=row.get("custom_js", ""),
    )

    if key in ("mode", "mod"):
        try:
            config.mode = AutomationMode(val)
        except ValueError:
            await update.message.reply_text(f"Invalid mode. Options: {[m.value for m in AutomationMode]}")
            return
    elif key in ("tabs", "tab_count"):
        config.tab_count = max(1, min(8, int(val)))
    elif key in ("refresh", "refresh_sec"):
        config.refresh_interval_sec = int(val)
    elif key in ("scroll", "scroll_sec"):
        config.scroll_interval_sec = int(val)
    elif key in ("proxy", "enable_proxy"):
        config.enable_proxy = val.lower() in ("1", "true", "yes", "on")
    elif key in ("spoof", "spoofing", "enable_spoofing"):
        config.enable_spoofing = val.lower() in ("1", "true", "yes", "on")
    elif key in ("randomize", "random"):
        config.randomize_intervals = val.lower() in ("1", "true", "yes", "on")
    else:
        await update.message.reply_text(f"Unknown key: {key}")
        return

    await repo.update_config(sid, config)
    await update.message.reply_text(f"✅ Updated `{key}` = `{val}`", parse_mode=ParseMode.MARKDOWN)


# ------------------------------------------------------------------
# /stats <id>
# ------------------------------------------------------------------
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        return
    sid = ctx.args[0]
    sr = ctx.bot_data.get("stats_repo")
    if sr is None:
        return
    s = await sr.get(sid)
    if not s:
        await update.message.reply_text("No stats yet")
        return
    text = (
        f"📊 *Stats* `{sid}`\n\n"
        f"Pages loaded: {s.get('pages_loaded', 0)}\n"
        f"Scrolls: {s.get('scrolls_performed', 0)}\n"
        f"Tabs switched: {s.get('tabs_switched', 0)}\n"
        f"JS execs: {s.get('js_executions', 0)}\n"
        f"Errors: {s.get('errors', 0)}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ------------------------------------------------------------------
# /screenshot <id>
# ------------------------------------------------------------------
async def cmd_screenshot(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        return
    sid = ctx.args[0]
    scheduler = ctx.bot_data.get("scheduler")
    if scheduler is None:
        return
    runner = await scheduler.get_runner(sid)
    if runner is None or not runner.tab_manager.all():
        await update.message.reply_text("No active tabs")
        return
    tab = runner.tab_manager.all()[0]
    settings = get_settings()
    path = Path(settings.SCREENSHOT_DIR) / f"{sid}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    ctx_pw = tab.context
    browser = ctx.bot_data.get("browser")
    if browser is None:
        return
    result = await browser.screenshot(ctx_pw, str(path))
    if result:
        with open(result, "rb") as f:
            await update.message.reply_photo(f)
    else:
        await update.message.reply_text("Screenshot failed")


# ------------------------------------------------------------------
# /events <id>
# ------------------------------------------------------------------
async def cmd_events(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        return
    sid = ctx.args[0]
    # Currently events are logged locally; just show last 5 log lines
    await update.message.reply_text(f"ℹ Events visible in bot logs for `{sid}`", parse_mode=ParseMode.MARKDOWN)


# ------------------------------------------------------------------
# /proxies
# ------------------------------------------------------------------
async def cmd_proxies(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    pm = ctx.bot_data.get("proxy_manager")
    if pm is None:
        return
    await update.message.reply_text(f"🌐 Proxy Pool: {pm.pool_size} active\n\n`/refresh_proxies` to update",
                                    parse_mode=ParseMode.MARKDOWN)


# ------------------------------------------------------------------
# /refresh_proxies
# ------------------------------------------------------------------
async def cmd_refresh_proxies(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    pm = ctx.bot_data.get("proxy_manager")
    if pm is None:
        return
    await update.message.reply_text("🔄 Refreshing…")
    count = await pm.refresh()
    await update.message.reply_text(f"✅ {count} proxies active.")


# ------------------------------------------------------------------
# /help
# ------------------------------------------------------------------
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*/add <url>* — New session for a URL\n"
        "*/list* — List sessions\n"
        "*/start <id>* — Start automation\n"
        "*/pause <id>* — Pause\n"
        "*/resume <id>* — Resume\n"
        "*/stop <id>* — Stop\n"
        "*/delete <id>* — Delete session\n"
        "*/tabs <id>* — List tabs\n"
        "*/add_tab <id>* — Add a tab\n"
        "*/remove_tab <id> <idx>* — Remove a tab\n"
        "*/config <id>* — View config\n"
        "*/config <id> key=val* — Update config\n"
        "*/stats <id>* — Session stats\n"
        "*/screenshot <id>* — Screenshot\n"
        "*/events <id>* — Events\n"
        "*/proxies* — Proxy pool\n"
        "*/refresh_proxies* — Refresh proxies\n"
        "*/help* — This message",
        parse_mode=ParseMode.MARKDOWN,
    )


# ------------------------------------------------------------------
# Register
# ------------------------------------------------------------------
def register(dispatcher) -> None:
    cmds = [
        ("start", cmd_start), ("add", cmd_add), ("list", cmd_list),
        ("sessions", cmd_list),
        ("start_session", cmd_start_session),
        ("pause", cmd_pause), ("resume", cmd_resume),
        ("stop", cmd_stop), ("delete", cmd_delete),
        ("tabs", cmd_tabs), ("add_tab", cmd_add_tab), ("remove_tab", cmd_remove_tab),
        ("config", cmd_config), ("stats", cmd_stats),
        ("screenshot", cmd_screenshot), ("events", cmd_events),
        ("proxies", cmd_proxies), ("refresh_proxies", cmd_refresh_proxies),
        ("help", cmd_help),
    ]
    for name, handler in cmds:
        dispatcher.add_handler(CommandHandler(name, handler, filters=ALLOWED), group=0)