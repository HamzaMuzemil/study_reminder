# scheduler.py
import logging
import random
from datetime import datetime, timedelta

import pytz
from sqlalchemy import select, func
from telegram.ext import Application, ContextTypes

from database import AsyncSessionLocal
from models import Project, ProgressLog, ReminderHistory, User
from services.coach_logic import calculate_metrics, calculate_smart_reminders, get_user_local_today, utc_now_naive
from messages.templates import get_alternating_quote, get_motivational_message, get_theme_pack, make_progress_bar
from config import get_system_timezone_name

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 10 * 60             # how often the tick runs
REMINDER_STALE_AFTER = timedelta(hours=2)   # older than this: mark Missed, don't send late
DAILY_SUMMARY_LOCAL_HOUR = 21               # send daily summary at/after 21:00 local
WEEKLY_SUMMARY_LOCAL_WEEKDAY = 6            # Python weekday(): Monday=0 ... Sunday=6
WEEKLY_SUMMARY_LOCAL_HOUR = 20              # send weekly summary at/after 20:00 local on that day


def _user_tz(user: User) -> pytz.BaseTzInfo:
    try:
        # Fallback to detected system timezone if UTC is set to ensure local alignment
        tz_name = user.timezone if user.timezone and user.timezone != "UTC" else get_system_timezone_name()
        return pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        return pytz.utc


def _parse_hhmm(value: str, fallback=(8, 0)) -> tuple[int, int]:
    try:
        h, m = map(int, value.split(":"))
        if 0 <= h < 24 and 0 <= m < 60:
            return h, m
    except Exception:
        pass
    return fallback


def is_user_awake(user: User) -> bool:
    """Verifies if the current system local time is inside the user's wake window."""
    tz = _user_tz(user)
    now_local = datetime.now(tz)

    try:
        wake_h, wake_m = map(int, user.wake_time.split(":"))
        sleep_h, sleep_m = map(int, user.sleep_time.split(":"))
    except Exception:
        wake_h, wake_m = 8, 0
        sleep_h, sleep_m = 23, 0

    now_minutes = now_local.hour * 60 + now_local.minute
    start_minutes = wake_h * 60 + wake_m
    end_minutes = sleep_h * 60 + sleep_m

    if end_minutes <= start_minutes:
        # Sleep window wraps past midnight, e.g. 08:00 to 02:00 (next day)
        return now_minutes >= start_minutes or now_minutes < end_minutes
    else:
        # Normal day window, e.g. 08:00 to 23:00
        return start_minutes <= now_minutes < end_minutes


async def run_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.id))
        user_ids = result.scalars().all()

    for uid in user_ids:
        async with AsyncSessionLocal() as session:
            try:
                user = await session.get(User, uid)
                if user is None:
                    continue
                await _process_user_tick(session, context, user)
                await session.commit()
            except Exception:
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

    await _maybe_send_weekly_summary(session, context, user, now_local, today_local)


async def _maybe_generate_reminders(session, user, projects, now_local, today_local) -> None:
    if user.last_reminder_gen_date == today_local:
        return

    wake_h, wake_m = _parse_hhmm(user.wake_time, (8, 0))
    wake_today = now_local.replace(hour=wake_h, minute=wake_m, second=0, microsecond=0)

    if now_local < wake_today:
        return

    run_times = calculate_smart_reminders(user, list(projects))
    for run_t_utc in run_times:
        session.add(ReminderHistory(user_id=user.id, scheduled_for=run_t_utc, status="Scheduled"))

    user.last_reminder_gen_date = today_local
    logger.info(f"Generated {len(run_times)} reminder slot(s) for user {user.id} on {today_local}")


async def _dispatch_due_reminders(session, context, user) -> None:
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

    # Enforce bedtime rules: If user is asleep, discard pending scheduled reminders to avoid waking them up.
    if not is_user_awake(user):
        for reminder in due:
            reminder.status = "Missed"
        return

    proj_res = await session.execute(
        select(Project).where(Project.user_id == user.id, Project.status == "Active")
    )
    projects = proj_res.scalars().all()

    for reminder in due:
        age = now_utc - reminder.scheduled_for
        if age > REMINDER_STALE_AFTER or not projects:
            reminder.status = "Missed"
            continue

        chosen_project = random.choice(projects)
        metrics = calculate_metrics(chosen_project, today=get_user_local_today(user))
        
        # Calculate indexes dynamically for alternating Amharic/English quotes
        log_res = await session.execute(
            select(func.count(ProgressLog.id)).join(Project).where(Project.user_id == user.id)
        )
        log_cnt = log_res.scalar() or 0
        rem_res = await session.execute(
            select(func.count(ReminderHistory.id)).where(ReminderHistory.user_id == user.id, ReminderHistory.status == "Sent")
        )
        rem_cnt = rem_res.scalar() or 0
        total_runs = log_cnt + rem_cnt

        quote = get_alternating_quote(total_runs)

        msg = get_motivational_message(
            project_name=chosen_project.name,
            remaining=metrics["daily_target"],
            unit=chosen_project.unit,
            pace=metrics["pace_status"],
            theme=user.theme,
            quote=quote
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
    if not is_user_awake(user):
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
            f"- Progress bar: {make_progress_bar(metrics['completion_pct'], user.theme)}\n"
            f"- Completion Progress: {metrics['completion_pct']}%\n\n"
        )

    # Calculate indexes dynamically for alternating Amharic/English quotes
    log_res = await session.execute(
        select(func.count(ProgressLog.id)).join(Project).where(Project.user_id == user.id)
    )
    log_cnt = log_res.scalar() or 0
    rem_res = await session.execute(
        select(func.count(ReminderHistory.id)).where(ReminderHistory.user_id == user.id, ReminderHistory.status == "Sent")
    )
    rem_cnt = rem_res.scalar() or 0
    total_runs = log_cnt + rem_cnt

    quote = get_alternating_quote(total_runs)
    summary_txt += f"💡 _\"{quote}\"_"

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
    if not is_user_awake(user):
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