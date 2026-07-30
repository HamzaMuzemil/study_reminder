# handlers/settings.py
import logging
from telegram import Update
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
from models import User
from keyboards.inline import get_settings_keyboard, get_main_menu_keyboard
from handlers.common import cancel, menu_callback_fallback

logger = logging.getLogger(__name__)

SET_TIMES, SET_FREQ, SET_STYLE = range(3)


# --- Helper functions for 12h/24h conversion ---

def parse_12h_to_24h(time_str: str) -> str:
    """
    Parses a 12-hour time string (e.g., '7:30 AM', '11 PM', '08:00 pm') 
    and returns a 24-hour 'HH:MM' string. Raises ValueError if invalid.
    """
    time_str = time_str.strip().upper()
    if "AM" not in time_str and "PM" not in time_str:
        raise ValueError("Missing AM/PM")
        
    clean_str = "".join(time_str.split())  # removes all spaces, e.g. "7:30AM"
    
    if clean_str.endswith("AM"):
        meridian = "AM"
        num_part = clean_str[:-2]
    elif clean_str.endswith("PM"):
        meridian = "PM"
        num_part = clean_str[:-2]
    else:
        raise ValueError("Invalid format")
        
    if ":" in num_part:
        h_str, m_str = num_part.split(":")
    else:
        h_str = num_part
        m_str = "00"
        
    h = int(h_str)
    m = int(m_str)
    
    if not (1 <= h <= 12 and 0 <= m < 60):
        raise ValueError("Hours must be 1-12, minutes 0-59")
        
    if meridian == "PM" and h != 12:
        h += 12
    elif meridian == "AM" and h == 12:
        h = 0
        
    return f"{h:02d}:{m:02d}"


def format_24h_to_12h(time_str: str) -> str:
    """
    Converts 'HH:MM' (24-hour) to 'HH:MM AM/PM' (12-hour) for display.
    """
    try:
        h, m = map(int, time_str.split(":"))
        meridian = "AM"
        if h >= 12:
            meridian = "PM"
            if h > 12:
                h -= 12
        elif h == 0:
            h = 12
        return f"{h:02d}:{m:02d} {meridian}"
    except Exception:
        return time_str


# --- Core Setting View ---

async def view_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    async with AsyncSessionLocal() as session:
        user_res = await session.execute(select(User).where(User.id == query.from_user.id))
        user = user_res.scalar_one_or_none()

    if not user:
        await query.edit_message_text("Couldn't load your settings. Try /start first.")
        return

    wake_12 = format_24h_to_12h(user.wake_time)
    sleep_12 = format_24h_to_12h(user.sleep_time)

    settings_text = (
        f"⚙️ *Your Settings*\n\n"
        f"⏰ *Wake / Sleep*: {wake_12} / {sleep_12}\n"
        f"📊 *Reminders*: {user.reminder_frequency}/day\n"
        f"🗣️ *Style*: {user.notification_style}\n\n"
        "Tap a setting below to change it:"
    )

    await query.edit_message_text(
        text=settings_text,
        parse_mode="Markdown",
        reply_markup=get_settings_keyboard()
    )


# --- Wake / Sleep time ---

async def start_set_sleep_wake(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⏰ *Set Wake/Sleep Times*\n\n"
        "Send both times in this format: `HH:MM AM/PM - HH:MM AM/PM`.\n"
        "_(Example: 07:30 AM - 11:00 PM or 7:30am - 11pm)_",
        parse_mode="Markdown",
    )
    return SET_TIMES


async def save_sleep_wake(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    try:
        parts = text.split("-", 1)
        if len(parts) != 2:
            raise ValueError("Missing hyphen separator")
        
        wake_part = parse_12h_to_24h(parts[0])
        sleep_part = parse_12h_to_24h(parts[1])
    except Exception:
        await update.message.reply_text(
            "Didn't quite catch that. Please use the 12-hour format: `HH:MM AM/PM - HH:MM AM/PM`\n"
            "_(Example: 07:30 AM - 11:00 PM)_:",
            parse_mode="Markdown"
        )
        return SET_TIMES

    async with AsyncSessionLocal() as session:
        user_res = await session.execute(select(User).where(User.id == update.effective_user.id))
        user = user_res.scalar_one_or_none()
        if user:
            user.wake_time = wake_part
            user.sleep_time = sleep_part
            await session.commit()

    await update.message.reply_text(
        "✅ Wake/sleep times updated! Reminders will use this from the next reminder batch onward.",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END


# --- Reminder frequency + notification style ---

async def start_set_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📊 *Set Reminder Frequency*\n\n"
        "How many study reminders would you like per day?\n"
        "_(Send a whole number from 1 to 6. Note: a high-importance or hard "
        "project may still add one extra reminder automatically, up to a cap of 6.)_",
        parse_mode="Markdown",
    )
    return SET_FREQ


async def save_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        freq = int(update.message.text.strip())
        if not (1 <= freq <= 6):
            raise ValueError
    except ValueError:
        await update.message.reply_text("Please send a whole number between 1 and 6:")
        return SET_FREQ

    context.user_data["new_frequency"] = freq

    await update.message.reply_text(
        "🗣️ Now pick a *Notification Style*:\n"
        "_(Send one of: Standard, Motivational, Direct)_",
        parse_mode="Markdown",
    )
    return SET_STYLE


async def save_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    style_text = update.message.text.strip().title()
    if style_text not in ("Standard", "Motivational", "Direct"):
        await update.message.reply_text("Please send exactly one of: Standard, Motivational, Direct:")
        return SET_STYLE

    freq = context.user_data.get("new_frequency", 3)

    async with AsyncSessionLocal() as session:
        user_res = await session.execute(select(User).where(User.id == update.effective_user.id))
        user = user_res.scalar_one_or_none()
        if user:
            user.reminder_frequency = freq
            user.notification_style = style_text
            await session.commit()

    await update.message.reply_text(
        f"✅ Reminders set to {freq}/day, style set to {style_text}.",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END


settings_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_set_sleep_wake, pattern="^set_sleep_wake$"),
        CallbackQueryHandler(start_set_frequency, pattern="^set_frequency$"),
    ],
    states={
        SET_TIMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_sleep_wake)],
        SET_FREQ: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_frequency)],
        SET_STYLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_style)],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        CallbackQueryHandler(menu_callback_fallback, pattern="^menu_")
    ],
    per_message=False
)