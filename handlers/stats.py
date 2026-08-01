# handlers/stats.py
import logging
from datetime import date, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from database import AsyncSessionLocal
from sqlalchemy import select, func
from models import Project, Streak, User, ProgressLog
from keyboards.inline import get_main_menu_keyboard
from messages.templates import get_theme_pack, make_progress_bar
from services.coach_logic import get_user_local_today

logger = logging.getLogger(__name__)


def get_active_streak_value(streak: Streak | None, today) -> int:
    """Calculates active streak safely relative to local today."""
    if not streak or not streak.last_activity_date:
        return 0
    if streak.last_activity_date < today - timedelta(days=1):
        return 0
    return streak.current_streak


async def view_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        # ----------------------------------------------------
        # 1. EXPERIENCE POINTS (XP) & LEVELS SYSTEM
        # ----------------------------------------------------
        # We treat 1 completed unit of study as 100 XP
        xp_res = await session.execute(
            select(func.sum(ProgressLog.amount_completed))
            .join(Project)
            .where(Project.user_id == user_id)
        )
        total_units = xp_res.scalar() or 0.0
        total_xp = int(total_units * 100)
        
        # Progression level calculation (1000 XP per Level)
        level = (total_xp // 1000) + 1
        xp_in_level = total_xp % 1000
        xp_pct = (xp_in_level / 1000.0) * 100
        xp_bar = make_progress_bar(xp_pct, theme)

        # Gamified Academic Ranks
        rank_titles = [
            "Novice Scribe 📜", "Apprentice Scribe 🖋️", "Junior Scholar 📚",
            "Scholar 🎓", "Senior Scholar 🧠", "Researcher 🔬", "Sage 🔮", "Grandmaster 👑"
        ]
        title_idx = min(level - 1, len(rank_titles) - 1)
        academic_rank = rank_titles[title_idx]

        # ----------------------------------------------------
        # 2. ANONYMOUS GLOBAL PERCENTILES ("SHADOW" COMPARE)
        # ----------------------------------------------------
        local_today = get_user_local_today(user) if user else date.today()
        current_streak_val = get_active_streak_value(streak, local_today)
        longest_streak_val = streak.longest_streak if streak else 0

        all_streaks_res = await session.execute(select(Streak))
        all_streaks = all_streaks_res.scalars().all()
        all_vals = [get_active_streak_value(s, local_today) for s in all_streaks]

        # Percentile rank calculation relative to the user base
        if len(all_vals) > 1:
            less_than = sum(1 for v in all_vals if v < current_streak_val)
            equal_to = sum(1 for v in all_vals if v == current_streak_val)
            percentile = ((less_than + 0.5 * equal_to) / len(all_vals)) * 100
            percentile = round(percentile, 1)
        else:
            percentile = 100.0

        # ----------------------------------------------------
        # 3. "BEAT YOUR GHOST" (SELF-COMPETITION)
        # ----------------------------------------------------
        seven_days_ago = local_today - timedelta(days=7)
        fourteen_days_ago = local_today - timedelta(days=14)

        # Current week total logs (Last 7 Days)
        curr_res = await session.execute(
            select(func.sum(ProgressLog.amount_completed))
            .join(Project)
            .where(Project.user_id == user_id, ProgressLog.logged_at >= seven_days_ago)
        )
        curr_total = round(curr_res.scalar() or 0.0, 1)

        # Previous week total logs (Days 8-14)
        prev_res = await session.execute(
            select(func.sum(ProgressLog.amount_completed))
            .join(Project)
            .where(
                Project.user_id == user_id, 
                ProgressLog.logged_at >= fourteen_days_ago,
                ProgressLog.logged_at < seven_days_ago
            )
        )
        prev_total = round(prev_res.scalar() or 0.0, 1)

    if not projects:
        empty_msg = f"{icons['warning']} You don't have any projects yet. Add one to start seeing stats here."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(empty_msg, reply_markup=get_main_menu_keyboard(theme))
        else:
            await update.message.reply_text(empty_msg, reply_markup=get_main_menu_keyboard(theme))
        return

    # Self-comparison output mapping
    if curr_total >= prev_total:
        comparison_txt = f"📈 *+{round(curr_total - prev_total, 1)} units* ahead of last week!"
    else:
        comparison_txt = f"📉 *-{round(prev_total - curr_total, 1)} units* behind last week's pace."

    total_active = sum(1 for p in projects if p.status == "Active")
    total_completed = sum(1 for p in projects if p.status == "Completed")

    stats_msg = (
        f"{icons['stats']} *Your Stats & Academics*:\n\n"
        f"🧙‍♂️ *Rank:* {academic_rank}\n"
        f"✨ *Level {level}:* ({total_xp} Total XP)\n"
        f"{xp_bar}\n"
        f"_{1000 - xp_in_level} XP needed to level up._\n\n"
        f"🔥 *Streaks & Percentiles*:\n"
        f"- Current: *{current_streak_val} days*\n"
        f"- Longest: *{longest_streak_val} days*\n"
        f"- Status: You are ahead of *{percentile}%* of learners!\n\n"
        f"👻 *Beat Your Ghost* (Week-over-Week):\n"
        f"- This Week: *{curr_total} units*\n"
        f"- Last Week: *{prev_total} units*\n"
        f"- Performance: {comparison_txt}\n\n"
        f"📂 *Projects Summary*:\n"
        f"- Active: {total_active}\n"
        f"- Completed: {total_completed}\n\n"
        f"🎯 Keep pushing forward! Use /start for the full menu."
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