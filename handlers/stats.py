import logging
from datetime import date, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from database import AsyncSessionLocal
from sqlalchemy import select
from models import Project, Streak, User
from keyboards.inline import get_main_menu_keyboard
from messages.templates import get_theme_pack
from services.coach_logic import get_user_local_today

logger = logging.getLogger(__name__)


def get_active_streak_value(streak: Streak | None, today) -> int:
    """
    Returns the streak's *current* value as of `today`, without touching
    the database.

    The stored current_streak column is only ever reset to 0 inside
    save_logged_progress -- i.e. only when the user next logs progress.
    Someone who logged 5 days in a row and then stops opening the bot
    keeps a current_streak of 5 sitting in the database indefinitely;
    nothing corrects it until they log again. Any place that *displays*
    the streak (not just the one place that updates it) needs to
    independently check whether it's actually still alive: a streak is
    only current if its last activity was today or yesterday relative to
    `today`. Anything older is stale and should read as 0, even though
    the stored row hasn't caught up yet.
    """
    if not streak or not streak.last_activity_date:
        return 0
    if streak.last_activity_date < today - timedelta(days=1):
        return 0
    return streak.current_streak


async def view_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /stats command, or the "📊 Statistics" button — shows streaks and a
    quick project count. Works the same either way it's reached.
    """
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        user_res = await session.execute(select(User).where(User.id == user_id))
        user = user_res.scalar_one_or_none()
        theme = user.theme if user else "Emoji"
        icons = get_theme_pack(theme)

        proj_res = await session.execute(select(Project).where(Project.user_id == user_id))
        projects = proj_res.scalars().all()

        streak_res = await session.execute(select(Streak).where(Streak.user_id == user_id))
        streak = streak_res.scalar_one_or_none()

    if not projects:
        empty_msg = f"{icons['warning']} You don't have any projects yet. Add one to start seeing stats here."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(empty_msg, reply_markup=get_main_menu_keyboard(theme))
        else:
            await update.message.reply_text(empty_msg, reply_markup=get_main_menu_keyboard(theme))
        return

    total_active = sum(1 for p in projects if p.status == "Active")
    total_completed = sum(1 for p in projects if p.status == "Completed")

    local_today = get_user_local_today(user) if user else date.today()
    current_streak_val = get_active_streak_value(streak, local_today)
    longest_streak_val = streak.longest_streak if streak else 0

    stats_msg = (
        f"{icons['stats']} *Your Stats*:\n\n"
        f"🔥 *Streak*:\n"
        f"- Current: *{current_streak_val} days*\n"
        f"- Longest: *{longest_streak_val} days*\n\n"
        f"📂 *Projects*:\n"
        f"- Active: {total_active}\n"
        f"- Completed: {total_completed}\n\n"
        f"🎯 Keep it up! Use /start for the full menu."
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            stats_msg, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(theme)
        )
    else:
        await update.message.reply_text(
            stats_msg, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(theme)
        )
