from datetime import date, datetime, timedelta, timezone
import random
import pytz
from models import Project, User


def utc_now_naive() -> datetime:
    """
    The current UTC time, as a naive datetime (no tzinfo attached).

    Every datetime stored in this project's database (scheduled_for,
    sent_at, joined_at, and so on) is a naive UTC datetime -- there's no
    timezone attached, but by convention it's always UTC. datetime.utcnow()
    used to be the standard way to get that, but it's deprecated as of
    newer Python versions. This gets the same value the supported way:
    ask for the real timezone-aware UTC time, then strip the tzinfo back
    off so it stays consistent with everything else already in the
    database and comparable to it directly.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_user_local_today(user: User) -> date:
    """
    Returns "today" as a date in the user's own timezone, not the server's.

    Why this matters: if the server runs in UTC and a user is in, say,
    US Eastern time, the two clocks disagree about what day it is for
    several hours around midnight. Using the server's date.today() for
    that user's deadlines, streaks, and daily logs would silently put
    things on the wrong day. Every place in this project that needs
    "today" for a specific user should go through this function instead
    of calling date.today() directly.
    """
    try:
        tz = pytz.timezone(user.timezone) if user and user.timezone else pytz.utc
    except pytz.UnknownTimeZoneError:
        tz = pytz.utc
    return datetime.now(tz).date()


def calculate_metrics(project: Project, today: date | None = None):
    """
    Calculates the daily/weekly pace targets and progress stats for one
    project.

    `today` should normally be supplied by the caller via
    get_user_local_today(project's owner) so the math lines up with that
    user's own calendar day. It falls back to the server's date.today()
    only so this function still works if ever called without user context
    (e.g. in a quick script or test).
    """
    if today is None:
        today = date.today()

    remaining_material = max(0.0, project.total_amount - project.completed_amount)

    if project.deadline < today:
        days_remaining = 0
    else:
        days_remaining = (project.deadline - today).days

    # Never divide by zero, even on the deadline day itself.
    divisor_days = max(days_remaining, 1)
    daily_target = round(remaining_material / divisor_days, 2)
    weekly_target = round(daily_target * 7, 2)

    completion_pct = round((project.completed_amount / project.total_amount) * 100, 1) if project.total_amount > 0 else 0
    remaining_pct = round(100 - completion_pct, 1)

    # Pace check: compare actual progress against where a perfectly even
    # pace would have the user by now.
    days_since_creation = (today - project.created_at.date()).days
    total_project_days = max((project.deadline - project.created_at.date()).days, 1)
    expected_daily_pace = project.total_amount / total_project_days
    expected_completed = expected_daily_pace * max(days_since_creation, 0)

    pace_status = "On Track"
    if project.completed_amount < expected_completed - (expected_daily_pace * 1.5):
        pace_status = "Behind Schedule"
    elif project.completed_amount > expected_completed + (expected_daily_pace * 1.5):
        pace_status = "Ahead of Schedule"

    # Estimated completion date, based on the user's own actual pace so far
    # (not the original plan) -- gives a realistic "if you keep going like
    # this" projection rather than just repeating the deadline back.
    if project.completed_amount > 0 and days_since_creation > 0:
        actual_daily_pace = project.completed_amount / days_since_creation
        if actual_daily_pace > 0:
            try:
                # An extremely slow actual pace (e.g. a sliver of progress
                # logged over a long stretch) can drive est_days_needed
                # into the millions. Capping it at 100 years keeps the
                # resulting date comfortably inside what Python's date
                # type can represent (year 9999), well before
                # today + timedelta(...) could raise OverflowError.
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
    """
    Picks randomized reminder times inside the user's own wake/sleep
    window for their own local "today", then converts each one to a
    naive UTC datetime for storage (everything in the database is UTC;
    only the *decision* of when "now" falls needs the user's timezone).

    Randomizes across [now, sleep_time] rather than [wake_time, sleep_time]
    whenever generation happens after wake time (e.g. the bot was offline
    over part of the wake window and only starts ticking again later).
    Randomizing across the full wake window and then pushing any
    already-passed draw to tomorrow would silently steal a slot from
    today's batch and hand it to tomorrow's -- which already gets its own
    fresh batch once its own generation runs -- so a single day could end
    up with a mix of tomorrow's real batch plus today's leftover push,
    while today itself came up short. Starting the random window at `now`
    instead means every draw this function returns is already in the
    future, so nothing needs to be deferred to another day at all.

    Returns an empty list if there's nothing active to remind about, or if
    there's no time left today between now and sleep time.
    """
    if not projects:
        return []

    try:
        tz = pytz.timezone(user.timezone) if user.timezone else pytz.utc
    except pytz.UnknownTimeZoneError:
        tz = pytz.utc

    now_local = datetime.now(tz)

    try:
        wake_h, wake_m = map(int, user.wake_time.split(":"))
        sleep_h, sleep_m = map(int, user.sleep_time.split(":"))
    except (ValueError, AttributeError):
        # Malformed or missing HH:MM string -- fall back to sane defaults
        # rather than crash the whole tick for every user because of one
        # bad settings row.
        wake_h, wake_m = 8, 0
        sleep_h, sleep_m = 23, 0

    base_reminders = user.reminder_frequency if user.reminder_frequency else 3

    # A project that's high-importance or hard gets one extra reminder
    # today, on top of the user's own chosen frequency.
    high_priority_active = any(p.importance == "High" or p.difficulty == "Hard" for p in projects)
    if high_priority_active:
        base_reminders += 1

    base_reminders = max(1, min(base_reminders, 6))

    start_minutes = wake_h * 60 + wake_m
    end_minutes = sleep_h * 60 + sleep_m
    if end_minutes <= start_minutes:
        end_minutes += 1440  # sleep time is past midnight relative to wake time

    # Never start the random draw earlier than "right now" -- this is the
    # piece that makes every generated time already be in the future.
    now_minutes = now_local.hour * 60 + now_local.minute
    effective_start = max(start_minutes, now_minutes)
    if effective_start >= end_minutes:
        return []  # no time left today between now and sleep time

    reminders_today = []
    for _ in range(base_reminders):
        rand_min = random.randint(effective_start, end_minutes)
        rem_hour = (rand_min // 60) % 24
        rem_min = rand_min % 60

        scheduled_local = now_local.replace(hour=rem_hour, minute=rem_min, second=0, microsecond=0)
        if rand_min >= 1440:
            scheduled_local += timedelta(days=1)

        reminders_today.append(scheduled_local.astimezone(pytz.utc).replace(tzinfo=None))

    reminders_today.sort()
    return reminders_today
