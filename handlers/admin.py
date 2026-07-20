import asyncio
import logging
from telegram import Update
from telegram.error import RetryAfter, Forbidden
from telegram.ext import ContextTypes
from config import Config
from database import AsyncSessionLocal
from sqlalchemy import select, func
from models import User, Project, ProgressLog

logger = logging.getLogger(__name__)

# Small delay between each broadcast message so a bot with many users
# doesn't trip Telegram's rate limits (roughly 30 messages/second overall).
# If ADMIN_USER_ID isn't set up, /admin and /broadcast simply won't work
# for anyone -- that's expected, not an error.
BROADCAST_DELAY_SECONDS = 0.05


async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/admin — quick usage stats. Only works for the ADMIN_USER_ID set in .env."""
    if Config.ADMIN_USER_ID == 0 or update.effective_user.id != Config.ADMIN_USER_ID:
        await update.message.reply_text("⛔ Access denied.")
        return

    async with AsyncSessionLocal() as session:
        user_cnt = await session.scalar(select(func.count(User.id)))
        proj_cnt = await session.scalar(select(func.count(Project.id)))
        logs_cnt = await session.scalar(select(func.count(ProgressLog.id)))

    admin_msg = (
        "🛠️ *Admin Stats*\n\n"
        f"👥 Total users: {user_cnt}\n"
        f"📚 Total projects: {proj_cnt}\n"
        f"📝 Total progress logs: {logs_cnt}"
    )

    await update.message.reply_text(admin_msg, parse_mode="Markdown")


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /broadcast <message> — sends a message to every registered user.
    Only works for the ADMIN_USER_ID set in .env.
    """
    if Config.ADMIN_USER_ID == 0 or update.effective_user.id != Config.ADMIN_USER_ID:
        await update.message.reply_text("⛔ Access denied.")
        return

    # context.args is pre-split on whitespace by PTB, so joining it back
    # with single spaces destroys any line breaks or indentation the admin
    # typed. Pulling the raw text and only stripping the leading command
    # token (which may itself be "/broadcast" or "/broadcast@BotName" in a
    # group chat) preserves the message exactly as written.
    broadcast_msg = update.message.text.partition(" ")[2].strip()
    if not broadcast_msg:
        await update.message.reply_text("Usage: `/broadcast <your message>`", parse_mode="Markdown")
        return

    async with AsyncSessionLocal() as session:
        users_res = await session.execute(select(User.id))
        user_ids = users_res.scalars().all()

    success_count = 0
    blocked_count = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 *Announcement*:\n\n{broadcast_msg}",
                parse_mode="Markdown"
            )
            success_count += 1
        except Forbidden:
            # User blocked the bot or deleted their account -- expected to
            # happen over time, not worth alarming the admin about each one.
            blocked_count += 1
        except RetryAfter as e:
            # Telegram is asking us to slow down; wait the time it tells
            # us to, then try this same user once more before moving on.
            logger.warning(f"Rate limited during broadcast; waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"📢 *Announcement*:\n\n{broadcast_msg}",
                    parse_mode="Markdown"
                )
                success_count += 1
            except Exception as retry_err:
                logger.warning(f"Failed to deliver broadcast to user {uid} after retry: {retry_err}")
        except Exception as e:
            logger.warning(f"Failed to deliver broadcast to user {uid}: {e}")

        await asyncio.sleep(BROADCAST_DELAY_SECONDS)

    summary = f"📢 Broadcast sent to {success_count} user(s)."
    if blocked_count:
        summary += f" ({blocked_count} had blocked the bot.)"
    await update.message.reply_text(summary)
