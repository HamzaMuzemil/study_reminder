"""
bot.py — Application entrypoint. This is the only file you ever run
directly (`python bot.py`); everything else is imported by it.

A note on how this starts up, in case you're curious: Application.run_polling()
is a *blocking* call — it creates and drives its own event loop internally.
So main() below is written as a plain, non-async function, and any async
setup work (like initializing the database) runs inside PTB's `post_init`
hook, which PTB itself awaits for us before polling begins.
"""

import logging
import warnings

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, TypeHandler
from telegram.warnings import PTBUserWarning

# A couple of this bot's conversations (adding a project, in particular)
# mix typed-text steps with button-tap steps in the same flow. That's a
# deliberate, working design choice -- python-telegram-bot has no way to
# express "mixed handler types, and I'm not using conversation_timeout or
# persistence" without also printing an informational warning about it.
# Since this bot genuinely doesn't use either of those features, the
# warning doesn't apply here. It's silenced explicitly, rather than left
# to print on every startup and look like something is broken.
#
# This must run BEFORE the handlers.* imports below, since those modules
# build their ConversationHandlers (and so trigger the warning) at import
# time, not when the bot actually starts running.
warnings.filterwarnings(
    "ignore",
    message=r"If 'per_message=False', 'CallbackQueryHandler' will not be tracked for every message\.",
    category=PTBUserWarning,
)

from config import Config
from database import init_db
from scheduler import setup_scheduler
from handlers.common import start, help_command, dashboard_callback, cancel, ensure_user_registered
from handlers.project import (
    add_project_conv_handler,
    edit_deadline_conv_handler,
    list_projects,
    list_archived_projects, 
    view_project_detail,
    handle_project_actions,
)
from handlers.progress import progress_conv_handler, start_log_progress
from handlers.settings import settings_conv_handler, view_settings
from handlers.stats import view_stats
from handlers.admin import admin_dashboard, admin_broadcast

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application) -> None:
    """Runs once, inside PTB's own event loop, before polling starts."""
    await init_db()
    logger.info("Database initialized.")


async def on_error(update, context) -> None:
    """
    Global fallback so one bad update (a malformed message, an unexpected
    callback, a network hiccup) can't silently kill a handler chain or
    crash the whole bot -- it just gets logged, and the bot keeps running.
    """
    logger.error("Unhandled exception while processing an update:", exc_info=context.error)


def main() -> None:
    if not Config.TELEGRAM_BOT_TOKEN:
        logger.critical(
            "TELEGRAM_BOT_TOKEN is not set. Check that your .env file exists, "
            "is named exactly '.env' (not '.env.txt'), and sits next to this "
            "file (bot.py)."
        )
        return

    application = (
        ApplicationBuilder()
        .token(Config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_error_handler(on_error)

    # Runs before every other handler, for every update, in its own group
    # (a lower group number runs first; groups don't stop each other the
    # way handlers within one group do). Its only job is guaranteeing a
    # User row exists before anything else touches the database on this
    # user's behalf -- see ensure_user_registered's docstring for why that
    # matters even for users who already used the bot before.
    application.add_handler(TypeHandler(Update, ensure_user_registered), group=-1)

    # Conversation handlers first -- they need first look at matching updates.
    application.add_handler(add_project_conv_handler)
    application.add_handler(edit_deadline_conv_handler)
    application.add_handler(progress_conv_handler)
    application.add_handler(settings_conv_handler)

    # Core commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", view_stats))
    application.add_handler(CommandHandler("done", start_log_progress))
    # /cancel is already wired as the fallback inside every conversation
    # (adding a project, editing settings, etc.) so it works mid-flow.
    # This registers it as a plain command too, so sending /cancel when
    # nothing is in progress still gets a reply instead of being silently
    # ignored.
    application.add_handler(CommandHandler("cancel", cancel))

    # Admin commands (only usable by the Telegram user ID set as
    # ADMIN_USER_ID in .env)
    application.add_handler(CommandHandler("admin", admin_dashboard))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))

   # Menu routing (the buttons on the main dashboard)
    application.add_handler(CallbackQueryHandler(dashboard_callback, pattern="^menu_main$"))
    application.add_handler(CallbackQueryHandler(list_projects, pattern="^menu_list_projects$"))
    application.add_handler(CallbackQueryHandler(list_archived_projects, pattern="^menu_archived_projects$"))  # <-- ADD THIS LINE
    application.add_handler(CallbackQueryHandler(view_stats, pattern="^menu_stats$"))
    application.add_handler(CallbackQueryHandler(view_settings, pattern="^menu_settings$"))
    application.add_handler(CallbackQueryHandler(help_command, pattern="^menu_help$"))

    # Project-specific actions (view/pause/resume/archive/delete a project)
    application.add_handler(CallbackQueryHandler(view_project_detail, pattern=r"^view_project_\d+$"))
    application.add_handler(
        CallbackQueryHandler(handle_project_actions, pattern=r"^proj_(pause|resume|archive|delete)_\d+$")
    )

    # Background scheduler: one recurring tick that generates and sends
    # reminders/summaries. See scheduler.py for how this works.
    setup_scheduler(application)

    logger.info("Study Coach Bot is starting polling...")
    application.run_polling()


if __name__ == "__main__":
    main()
