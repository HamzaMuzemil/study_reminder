"""
scheduler.py

There is exactly ONE scheduler in this whole project: python-telegram-bot's
own built-in `application.job_queue`. It registers a single recurring "tick"
job that runs every TICK_INTERVAL_SECONDS.

On every tick, for every user, in that user's own local time, this file:
  1. Generates today's random reminder slots, once per user per local day.
  2. Sends any reminder slots that are now due.
  3. Sends the daily summary, once per user per local day, after a local hour.
  4. Sends the weekly summary, once per user per local week, on a local
     weekday/hour.

Why one DB-driven tick instead of scheduling each reminder as its own
one-off job:
  A one-off job (job_queue.run_once) only lives in memory. If the bot
  process restarts -- a crash, a deploy, your laptop going to sleep --
  every not-yet-fired job for the rest of the day disappears with no
  record it ever existed. A tick that re-reads "what's due right now"
  from the database every time it runs doesn't have that problem: whatever
  the process was doing before a restart, the very next tick just picks up
  wherever the saved state says it should be. That's the difference between
  "reminders occasionally arrive a few minutes late" and "reminders
  silently vanish for the rest of the day whenever the bot restarts."

Trade-off: reminders and summaries fire within one tick interval (default
10 minutes) of their target time, not to-the-minute. That's a fine trade
for a study-reminder bot, and far better than the alternative.
"""

import logging
import random
from datetime import datetime, timedelta

import pytz
from sqlalchemy import select
from telegram.ext import Application, ContextTypes

from database import AsyncSessionLocal
from models import Project, ProgressLog, ReminderHistory, User
from services.coach_logic import calculate_metrics, calculate_smart_reminders, get_user_local_today, utc_now_naive
from messages.templates import QUOTES, get_motivational_message, get_theme_pack

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 10 * 60             # how often the tick runs
REMINDER_STALE_AFTER = timedelta(hours=2)   # older than this: mark Missed, don't send late
DAILY_SUMMARY_LOCAL_HOUR = 21               # send daily summary at/after 21:00 local
WEEKLY_SUMMARY_LOCAL_WEEKDAY = 6            # Python weekday(): Monday=0 ... Sunday=6
WEEKLY_SUMMARY_LOCAL_HOUR = 20              # send weekly summary at/after 20:00 local on that day


def _user_tz(user: User) -> pytz.BaseTzInfo:
    """Safely resolves a user's stored timezone string, defaulting to UTC
    for anything missing or invalid so one bad row can't break the tick
    for every other user."""
    try:
        return pytz.timezone(user.timezone) if user.timezone else pytz.utc
    except pytz.UnknownTimeZoneError:
        logger.warning(f"Unknown timezone '{user.timezone}' for user {user.id}; defaulting to UTC")
        return pytz.utc


def _parse_hhmm(value: str, fallback=(8, 0)) -> tuple[int, int]:
    try:
        h, m = map(int, value.split(":"))
        if 0 <= h < 24 and 0 <= m < 60:
            return h, m
    except Exception:
        pass
    return fallback


async def run_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Single entry point invoked every TICK_INTERVAL_SECONDS by PTB's job_queue.

    Each user gets their own session and their own commit. Sharing one
    session (and one commit) across every user in the tick meant a single
    failure partway through -- a bad row, a brief database lock on commit,
    any exception at all -- rolled back the *entire* transaction, including
    reminders that had already been successfully sent to Telegram earlier
    in the same loop. Those reminder rows would still show status
    "Scheduled" after the rollback, so the next tick would see them as due
    again and re-send them. Committing per-user closes that window: once a
    user's tick is committed, nothing that happens to a later user in the
    same run can undo it.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.id))
        user_ids = result.scalars().all()

    for uid in user_ids:
        async with AsyncSessionLocal() as session:
            try:
                user = await session.get(User, uid)
                if user is None:
                    # Deleted between the id query above and now -- nothing
                    # to process.
                    continue
                await _process_user_tick(session, context, user)
                await session.commit()
            except Exception:
                # One user's bad data or a delivery failure should never
                # stop every other user's reminders from being processed,
                # and must not roll back any other user's already-committed
                # tick.
                logger.exception(f"Tick processing failed for user {uid}")


async def _process_user_tick(session, context, user: User) -> None:
    tz = _user_tz(user)
    now_local = datetime.now(tz)
    today_local = now_local.date()

    proj_res = await session.execute(
        select(Project).where(Project.user_id == user.id, Project.status == "Active")
    )
    projects = proj_res.scalars().all()

    if projects:
        await _maybe_generate_reminders(session, user, projects, now_local, today_local)
        await _dispatch_due_reminders(session, context, user)
        await _maybe_send_daily_summary(session, context, user, projects, now_local, today_local)

    # Weekly summary can still be worth sending even with zero active
    # projects right now (e.g. "you completed 2 projects this week").
    await _maybe_send_weekly_summary(session, context, user, now_local, today_local)


async def _maybe_generate_reminders(session, user, projects, now_local, today_local) -> None:
    """Generates today's reminder slots once per user per local day.

    Storing `last_reminder_gen_date` on the User row (rather than just
    checking "do any Scheduled rows exist for today") is what makes this
    safe to call every single tick without ever generating duplicates,
    and it's a plain database column so it survives a restart correctly.
    """
    if user.last_reminder_gen_date == today_local:
        return

    wake_h, wake_m = _parse_hhmm(user.wake_time, (8, 0))
    wake_today = now_local.replace(hour=wake_h, minute=wake_m, second=0, microsecond=0)

    # Don't generate before the user is even awake yet today; the next
    # tick after their wake time will generate normally.
    if now_local < wake_today:
        return

    run_times = calculate_smart_reminders(user, list(projects))
    for run_t_utc in run_times:
        session.add(ReminderHistory(user_id=user.id, scheduled_for=run_t_utc, status="Scheduled"))

    user.last_reminder_gen_date = today_local
    logger.info(f"Generated {len(run_times)} reminder slot(s) for user {user.id} on {today_local}")


async def _dispatch_due_reminders(session, context, user) -> None:
    """Sends any reminder that is currently due, by asking the database
    what's due right now -- not by trusting an in-memory job to still
    exist. This is the part that makes restarts safe: even if the bot
    was down when a reminder was supposed to fire, the row is still
    sitting there with status="Scheduled", and this query finds it on
    the next tick after startup."""
    now_utc = utc_now_naive()

    due_res = await session.execute(
        select(ReminderHistory).where(
            ReminderHistory.user_id == user.id,
            ReminderHistory.status == "Scheduled",
            ReminderHistory.scheduled_for <= now_utc,
        )
    )
    due = due_res.scalars().all()
    if not due:
        return

    proj_res = await session.execute(
        select(Project).where(Project.user_id == user.id, Project.status == "Active")
    )
    projects = proj_res.scalars().all()

    for reminder in due:
        age = now_utc - reminder.scheduled_for
        if age > REMINDER_STALE_AFTER or not projects:
            # Too old to be a useful nudge (e.g. bot was down for hours),
            # or the user has nothing active left to be reminded about.
            reminder.status = "Missed"
            continue

        chosen_project = random.choice(projects)
        metrics = calculate_metrics(chosen_project, today=get_user_local_today(user))
        msg = get_motivational_message(
            project_name=chosen_project.name,
            remaining=metrics["daily_target"],
            unit=chosen_project.unit,
            pace=metrics["pace_status"],
            theme=user.theme,
        )
        try:
            await context.bot.send_message(chat_id=user.id, text=msg, parse_mode="Markdown")
            reminder.status = "Sent"
            reminder.sent_at = utc_now_naive()
        except Exception as e:
            logger.error(f"Failed to deliver reminder to {user.id}: {e}")
            reminder.status = "Missed"


async def _maybe_send_daily_summary(session, context, user, projects, now_local, today_local) -> None:
    if not user.daily_summary_enabled:
        return
    if user.last_daily_summary_date == today_local:
        return
    if now_local.hour < DAILY_SUMMARY_LOCAL_HOUR:
        return

    icons = get_theme_pack(user.theme)
    summary_txt = f"{icons['stats']} *Daily Progress Summary* ({today_local.isoformat()}):\n\n"

    for p in projects:
        metrics = calculate_metrics(p, today=today_local)
        log_res = await session.execute(
            select(ProgressLog).where(ProgressLog.project_id == p.id, ProgressLog.logged_at == today_local)
        )
        logged_today = sum(log.amount_completed for log in log_res.scalars().all())
        summary_txt += (
            f"📚 *{p.name}*:\n"
            f"- Done Today: {logged_today} {p.unit}\n"
            f"- Target set: {metrics['daily_target']} {p.unit}\n"
            f"- Completion Progress: {metrics['completion_pct']}%\n\n"
        )

    summary_txt += f"💡 _\"{random.choice(QUOTES)}\"_"

    try:
        await context.bot.send_message(chat_id=user.id, text=summary_txt, parse_mode="Markdown")
        user.last_daily_summary_date = today_local
    except Exception as e:
        logger.error(f"Failed to deliver daily summary to {user.id}: {e}")


async def _maybe_send_weekly_summary(session, context, user, now_local, today_local) -> None:
    if not user.weekly_summary_enabled:
        return
    if user.last_weekly_summary_date == today_local:
        return
    if now_local.weekday() != WEEKLY_SUMMARY_LOCAL_WEEKDAY:
        return
    if now_local.hour < WEEKLY_SUMMARY_LOCAL_HOUR:
        return

    proj_res = await session.execute(select(Project).where(Project.user_id == user.id))
    projects = proj_res.scalars().all()
    if not projects:
        return

    one_week_ago = today_local - timedelta(days=7)
    icons = get_theme_pack(user.theme)
    completed_projs = len([p for p in projects if p.status == "Completed"])

    summary_txt = (
        f"{icons['star']} *Weekly Performance Report* {icons['star']}\n\n"
        f"📈 Completed Projects: {completed_projs}\n"
    )

    total_logs = 0
    daily_performance: dict = {}
    for p in projects:
        log_res = await session.execute(
            select(ProgressLog).where(
                ProgressLog.project_id == p.id,
                ProgressLog.logged_at >= one_week_ago,
            )
        )
        logs = log_res.scalars().all()
        total_logs += len(logs)
        for l in logs:
            daily_performance[l.logged_at] = daily_performance.get(l.logged_at, 0.0) + l.amount_completed

    if daily_performance:
        best_day_date = max(daily_performance, key=daily_performance.get)
        best_day_str = f"{best_day_date} ({daily_performance[best_day_date]} units)"
    else:
        best_day_str = "N/A"

    summary_txt += (
        f"🔥 Activity Events: {total_logs} sessions logged\n"
        f"🏆 Top Study Session: {best_day_str}\n\n"
        f"Stay determined! Every incremental step compounds toward success."
    )

    try:
        await context.bot.send_message(chat_id=user.id, text=summary_txt, parse_mode="Markdown")
        user.last_weekly_summary_date = today_local
    except Exception as e:
        logger.error(f"Failed to deliver weekly summary to {user.id}: {e}")


def setup_scheduler(application: Application) -> None:
    """
    Registers the single recurring tick job on PTB's own job_queue.

    Requires the bot to be installed with the `job-queue` extra:
        pip install "python-telegram-bot[job-queue]"
    (already set correctly in requirements.txt).
    """
    if application.job_queue is None:
        raise RuntimeError(
            "JobQueue is not available. Install with: "
            'pip install "python-telegram-bot[job-queue]"'
        )

    application.job_queue.run_repeating(
        run_tick,
        interval=TICK_INTERVAL_SECONDS,
        first=10,  # small delay after startup before the first tick
        name="study_coach_tick",
    )
    logger.info(f"Scheduler registered: one tick every {TICK_INTERVAL_SECONDS}s, restart-safe.")
