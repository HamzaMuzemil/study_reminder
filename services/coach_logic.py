# services/coach_logic.py
from datetime import datetime, date, timezone, timedelta
import math
import random
import pytz
from models import Project, User


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_user_local_today(user: User) -> date:
    try:
        # Defaults to Addis Ababa instead of UTC to align with local clock
        tz_name = user.timezone if user and user.timezone and user.timezone != "UTC" else "Africa/Addis_Ababa"
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.timezone("Africa/Addis_Ababa")
    return datetime.now(tz).date()


def calculate_metrics(project: Project, today: date | None = None):
    if today is None:
        today = date.today()

    remaining_material = max(0.0, project.total_amount - project.completed_amount)

    if project.deadline < today:
        days_remaining = 0
    else:
        days_remaining = (project.deadline - today).days

    divisor_days = max(days_remaining, 1)
    raw_target = remaining_material / divisor_days

    # ----------------------------------------------------
    # ADAPTIVE PACING (DEFICIT SMOOTHING)
    # ----------------------------------------------------
    total_project_days = max((project.deadline - project.created_at.date()).days, 1)
    original_pace = project.total_amount / total_project_days
    
    days_since_creation = max(0, (today - project.created_at.date()).days)
    expected_completed = original_pace * days_since_creation
    deficit = max(0.0, expected_completed - project.completed_amount)

    if deficit > 0 and days_remaining > 0:
        smoothing_window = 4
        effective_days = days_remaining + smoothing_window
        adaptive_target = original_pace + (deficit / effective_days)
        daily_target = round(min(adaptive_target, raw_target), 2)
    else:
        daily_target = round(raw_target, 2)

    weekly_target = round(daily_target * 7, 2)

    completion_pct = round((project.completed_amount / project.total_amount) * 100, 1) if project.total_amount > 0 else 0
    remaining_pct = round(100 - completion_pct, 1)

    pace_status = "On Track"
    if project.completed_amount < expected_completed - (original_pace * 1.5):
        pace_status = "Behind Schedule"
    elif project.completed_amount > expected_completed + (original_pace * 1.5):
        pace_status = "Ahead of Schedule"

    if project.completed_amount > 0 and days_since_creation > 0:
        actual_daily_pace = project.completed_amount / days_since_creation
        if actual_daily_pace > 0:
            try:
                est_days_needed = min(remaining_material / actual_daily_pace, 36500)
                est_completion_date = today + timedelta(days=int(est_days_needed))
            except (OverflowError, ValueError):
                est_completion_date = project.deadline
            else:
                est_completion_date = project.deadline
    else:
        est_completion_date = project.deadline

    return {
        "days_remaining": days_remaining,
        "remaining_material": remaining_material,
        "daily_target": daily_target,
        "weekly_target": weekly_target,
        "completion_pct": completion_pct,
        "remaining_pct": remaining_pct,
        "pace_status": pace_status,
        "estimated_completion": est_completion_date,
    }


def calculate_smart_reminders(user: User, projects: list[Project]) -> list[datetime]:
    if not projects:
        return []

    try:
        # Defaults to Addis Ababa instead of UTC to align with local clock
        tz_name = user.timezone if user.timezone and user.timezone != "UTC" else "Africa/Addis_Ababa"
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.timezone("Africa/Addis_Ababa")

    now_local = datetime.now(tz)

    try:
        wake_h, wake_m = map(int, user.wake_time.split(":"))
        sleep_h, sleep_m = map(int, user.sleep_time.split(":"))
    except (ValueError, AttributeError):
        wake_h, wake_m = 8, 0
        sleep_h, sleep_m = 23, 0

    base_reminders = user.reminder_frequency if user.reminder_frequency else 3

    high_priority_active = any(p.importance == "High" or p.difficulty == "Hard" for p in projects)
    if high_priority_active:
        base_reminders += 1

    base_reminders = max(1, min(base_reminders, 6))

    start_minutes = wake_h * 60 + wake_m
    end_minutes = sleep_h * 60 + sleep_m
    if end_minutes <= start_minutes:
        end_minutes += 1440

    total_minutes = end_minutes - start_minutes
    now_minutes = now_local.hour * 60 + now_local.minute

    step = total_minutes / base_reminders
    reminders_today = []

    for i in range(base_reminders):
        slot_start = start_minutes + int(i * step)
        slot_end = start_minutes + int((i + 1) * step)

        if now_minutes >= slot_end:
            continue

        effective_start = max(slot_start, now_minutes)
        rand_min = random.randint(effective_start, slot_end)

        rem_hour = (rand_min // 60) % 24
        rem_min = rand_min % 60

        scheduled_local = now_local.replace(hour=rem_hour, minute=rem_min, second=0, microsecond=0)
        if rand_min >= 1440:
            scheduled_local += timedelta(days=1)

        reminders_today.append(scheduled_local.astimezone(pytz.utc).replace(tzinfo=None))

    return sorted(reminders_today)