# config.py
import os
from dotenv import load_dotenv

load_dotenv()


def _parse_admin_id(raw: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///study_coach.db")
    ADMIN_USER_ID = _parse_admin_id(os.getenv("ADMIN_USER_ID", "0"))

    # Configured defaults - updated standard default timezone explicitly to East Africa Time (Addis Ababa)
    DEFAULT_WAKE_TIME = "08:00"
    DEFAULT_SLEEP_TIME = "23:00"
    DEFAULT_TIMEZONE = "Africa/Addis_Ababa"
    DEFAULT_LANGUAGE = "en"
    DEFAULT_FREQUENCY = 3  # reminders per day