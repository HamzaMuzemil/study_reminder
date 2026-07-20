import os
from dotenv import load_dotenv

load_dotenv()


def _parse_admin_id(raw: str) -> int:
    """
    Turns the ADMIN_USER_ID value from .env into an int.

    Beginners following the README are told they can skip setting this.
    If they leave it blank, delete it, or leave a stray placeholder like
    "your_id_here", a plain int(raw) call would crash the whole bot before
    it even starts, with an error that doesn't explain what went wrong.
    This falls back to 0 (meaning "no admin configured") instead.
    """
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///study_coach.db")
    ADMIN_USER_ID = _parse_admin_id(os.getenv("ADMIN_USER_ID", "0"))

    # Defaults applied to a brand-new user (see models.py User columns).
    # Keep these two lists in sync if you ever change one.
    DEFAULT_WAKE_TIME = "08:00"
    DEFAULT_SLEEP_TIME = "23:00"
    DEFAULT_TIMEZONE = "UTC"
    DEFAULT_LANGUAGE = "en"
    DEFAULT_FREQUENCY = 3  # reminders per day
