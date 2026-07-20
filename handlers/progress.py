# handlers/progress.py
import logging
from datetime import date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.helpers import escape_markdown
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from database import AsyncSessionLocal
from sqlalchemy import select
from models import Project, ProgressLog, Streak, User
from keyboards.inline import get_main_menu_keyboard
from services.coach_logic import calculate_metrics, get_user_local_today
from messages.templates import make_progress_bar
from handlers.common import cancel, menu_callback_fallback

logger = logging.getLogger(__name__)

SELECT_PROJ, LOG_AMOUNT = range(2)


async def start_log_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        proj_res = await session.execute(
            select(Project).where(Project.user_id == user_id, Project.status == "Active")
        )
        projects = proj_res.scalars().all()
        user_res = await session.execute(select(User).where(User.id == user_id))
        user = user_res.scalar_one_or_none()
        theme = user.theme if user else "Emoji"

    if not projects:
        msg = "You don't have any active projects to log progress on. Add one first with ➕ New Project."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(msg, reply_markup=get_main_menu_keyboard(theme))
        else:
            await update.message.reply_text(msg, reply_markup=get_main_menu_keyboard(theme))
        return ConversationHandler.END

    # Generate inline buttons for active projects
    keyboard_buttons = []
    for p in projects:
        keyboard_buttons.append([InlineKeyboardButton(p.name, callback_data=f"log_select_{p.id}")])
    keyboard_buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="menu_main")])
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)

    text = "📚 *Which project did you make progress on?*\n\nSelect a project below:"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

    return SELECT_PROJ


async def handle_project_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    try:
        project_id = int(query.data.replace("log_select_", ""))
    except ValueError:
        await query.edit_message_text("Invalid project selection. Please try again.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    async with AsyncSessionLocal() as session:
        proj_res = await session.execute(select(Project).where(Project.id == project_id))
        p = proj_res.scalar_one_or_none()

    if not p or p.user_id != update.effective_user.id or p.status != "Active":
        await query.edit_message_text("This project is not currently active or could not be found.", reply_markup=get_main_menu_keyboard())
        return ConversationHandler.END

    context.user_data["log_project_id"] = project_id
    
    cancel_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="menu_main")]])
    await query.edit_message_text(
        f"📥 How much did you complete for *{escape_markdown(p.name, version=1)}*?\n"
        f"_(Enter a number in {p.unit})_",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard
    )
    return LOG_AMOUNT


async def save_logged_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Please enter a positive number (e.g., 5 or 12.5):")
        return LOG_AMOUNT

    project_id = context.user_data.get("log_project_id")
    if project_id is None:
        await update.message.reply_text("Session expired. Please start again with /done.")
        return ConversationHandler.END

    user_id = update.effective_user.id
    congrats_txt = None
    milestone_txt = None

    async with AsyncSessionLocal() as session:
        user_res = await session.execute(select(User).where(User.id == user_id))
        user = user_res.scalar_one_or_none()
        theme = user.theme if user else "Emoji"
        today = get_user_local_today(user) if user else date.today()

        proj_res = await session.execute(select(Project).where(Project.id == project_id))
        p = proj_res.scalar_one_or_none()

        if not p or p.user_id != user_id:
            await update.message.reply_text("Error loading that project. It may have been deleted.")
            return ConversationHandler.END

        p.completed_amount = min(p.total_amount, p.completed_amount + amount)

        new_log = ProgressLog(project_id=project_id, amount_completed=amount, logged_at=today)
        session.add(new_log)

        if p.completed_amount >= p.total_amount:
            p.status = "Completed"
            congrats_txt = f"🏆 *Congratulations!* You've finished *{escape_markdown(p.name, version=1)}*!"

        streak_res = await session.execute(select(Streak).where(Streak.user_id == user_id))
        streak = streak_res.scalar_one_or_none()

        if streak:
            if streak.last_activity_date is None:
                streak.current_streak = 1
                streak.last_activity_date = today
            elif streak.last_activity_date == today - timedelta(days=1):
                streak.current_streak += 1
                streak.last_activity_date = today
            elif streak.last_activity_date < today - timedelta(days=1):
                streak.current_streak = 1
                streak.last_activity_date = today

            if streak.current_streak > streak.longest_streak:
                streak.longest_streak = streak.current_streak

            if streak.current_streak in (7, 30, 100):
                milestone_txt = (
                    f"🔥 *Streak milestone!* You've studied "
                    f"{streak.current_streak} days in a row!"
                )

        await session.commit()
        metrics = calculate_metrics(p, today=today)
        proj_name = escape_markdown(p.name, version=1)
        proj_unit = p.unit
        completed_amount = p.completed_amount
        total_amount = p.total_amount

    if congrats_txt:
        await update.message.reply_text(congrats_txt, parse_mode="Markdown")
    if milestone_txt:
        await update.message.reply_text(milestone_txt, parse_mode="Markdown")

    bar_str = make_progress_bar(metrics['completion_pct'], theme)

    success_msg = (
        f"✅ *Progress logged!*\n\n"
        f"📘 Project: *{proj_name}*\n"
        f"📥 Added: +{amount} {proj_unit}\n"
        f"📊 Completed: {completed_amount}/{total_amount} {proj_unit}\n"
        f"📈 Progress: {bar_str}\n\n"
        f"🎯 Updated daily target: *{metrics['daily_target']} {proj_unit}/day*"
    )

    await update.message.reply_text(success_msg, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(theme))
    return ConversationHandler.END


progress_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_log_progress, pattern="^menu_log_progress$"),
        CommandHandler("done", start_log_progress),
    ],
    states={
        SELECT_PROJ: [CallbackQueryHandler(handle_project_selection, pattern=r"^log_select_\d+$")],
        LOG_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_logged_progress)],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        CallbackQueryHandler(menu_callback_fallback, pattern="^menu_")
    ],
    per_message=False
)