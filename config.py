# config.py
import os
from dotenv import load_dotenv

load_dotenv()


def _parse_admin_id(raw: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def get_system_timezone_name() -> str:
    """
    Dynamically detects the local host machine's timezone.
    Falls back to UTC if detection fails.
    """
    try:
        for path in ["/etc/timezone", "/var/db/zoneinfo"]:
            if os.path.exists(path):
                with open(path, "r") as f:
                    return f.read().strip()
    except Exception:
        pass

    try:
        import datetime
        offset = datetime.datetime.now().astimezone().utcoffset()
        offset_hours = offset.total_seconds() / 3600.0
        
        # Match offsets with standard location codes
        if offset_hours == 3.0:
            return "Africa/Addis_Ababa"
        elif offset_hours == 2.0:
            return "Europe/Paris"
        elif offset_hours == 1.0:
            return "Europe/London"
        elif offset_hours == 0.0:
            return "UTC"
        elif offset_hours == -5.0:
            return "America/New_York"
        elif offset_hours == -6.0:
            return "America/Chicago"
        elif offset_hours == -8.0:
            return "America/Los_Angeles"
        elif offset_hours == 5.5:
            return "Asia/Kolkata"
        
        # Dynamic search lookup
        import pytz
        now = datetime.datetime.now()
        for name in pytz.all_timezones:
            tz = pytz.timezone(name)
            if now.astimezone(tz).utcoffset() == offset:
                return name
    except Exception:
        pass

    return "UTC"


class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///study_coach.db")
    ADMIN_USER_ID = _parse_admin_id(os.getenv("ADMIN_USER_ID", "0"))

    # Configured defaults
    DEFAULT_WAKE_TIME = "08:00"
    DEFAULT_SLEEP_TIME = "23:00"
    DEFAULT_TIMEZONE = get_system_timezone_name()
    DEFAULT_LANGUAGE = "en"
    DEFAULT_FREQUENCY = 3  # reminders per day