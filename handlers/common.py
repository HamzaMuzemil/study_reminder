# handlers/common.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import AsyncSessionLocal
from sqlalchemy import select
from models import User, Streak
from keyboards.inline import get_main_menu_keyboard
from messages.templates import get_theme_pack

logger = logging.getLogger(__name__)


async def get_or_create_user(session, telegram_user) -> User:
    result = await session.execute(select(User).where(User.id == telegram_user.id))
    user = result.scalar_one_or_none()
    if user:
        return user

    user = User(id=telegram_user.id, username=telegram_user.username)
    session.add(user)
    session.add(Streak(user_id=telegram_user.id))
    await session.commit()
    logger.info(f"Registered new bot user: {telegram_user.id}")
    return user


async def ensure_user_registered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_tg = update.effective_user
    if user_tg is None:
        return
    async with AsyncSessionLocal() as session:
        await get_or_create_user(session, user_tg)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_tg = update.effective_user

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, user_tg)
        theme = user.theme

    icons = get_theme_pack(theme)
    welcome_text = (
        f"{icons['star']} *Welcome to your Study Coach, {user_tg.first_name}!* {icons['star']}\n\n"
        "Let's turn your study material into a clear daily plan. "
        "Use the buttons below to add a project, log progress, or check your stats."
    )

    await update.message.reply_text(
        text=welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(theme)
    )


async def dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.id == query.from_user.id))
        user = res.scalar_one_or_none()
        theme = user.theme if user else "Emoji"

    icons = get_theme_pack(theme)
    welcome_text = (
        f"{icons['star']} *Study Coach Dashboard* {icons['star']}\n\n"
        "Pick an option below to manage your projects, check your progress, "
        "or adjust your settings."
    )

    await query.edit_message_text(
        text=welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(theme)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Study Coach Bot Guide*\n\n"
        "*How it works:*\n"
        "• *Projects*: one project per thing you're studying (e.g. a lecture "
        "set or a textbook). You tell it the total amount and the deadline.\n"
        "• *Daily target*: the bot works out how much you need to do each day "
        "to finish on time, and recalculates it every time you log progress.\n"
        "• *Reminders*: a few times a day, only between your wake and sleep "
        "times, it'll nudge you with your current target.\n\n"
        "*Commands:*\n"
        "/start - Open the dashboard\n"
        "/done - Quickly log progress on a project\n"
        "/stats - See your streak and overall stats\n"
        "/cancel - Exit out of anything you're in the middle of"
    )

    # Resolve theme for back button
    async with AsyncSessionLocal() as session:
        uid = update.effective_user.id
        user_res = await session.execute(select(User).where(User.id == uid))
        user = user_res.scalar_one_or_none()
        theme = user.theme if user else "Emoji"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text=text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(theme)
        )
    else:
        await update.message.reply_text(
            text=text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(theme)
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main")]])
    await update.message.reply_text(
        "❌ Action cancelled.",
        reply_markup=keyboard
    )
    return ConversationHandler.END


async def menu_callback_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Universal fallback interceptor. If a user is in any conversation
    and clicks a main menu button, it will cancel the active conversation
    and immediately transition to the selected screen.
    """
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    data = query.data
    
    # Avoid circular import at import-time by importing on-demand inside the function
    if data == "menu_main":
        await dashboard_callback(update, context)
    elif data == "menu_list_projects":
        from handlers.project import list_projects
        await list_projects(update, context)
    elif data == "menu_log_progress":
        from handlers.progress import start_log_progress
        await start_log_progress(update, context)
    elif data == "menu_stats":
        from handlers.stats import view_stats
        await view_stats(update, context)
    elif data == "menu_settings":
        from handlers.settings import view_settings
        await view_settings(update, context)
    elif data == "menu_help":
        await help_command(update, context)
    elif data == "menu_new_project":
        from handlers.project import start_add_project
        await start_add_project(update, context)
    else:
        await query.answer()
        await dashboard_callback(update, context)

    return ConversationHandler.END