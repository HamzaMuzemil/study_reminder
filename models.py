# models.py
from datetime import datetime, date, timezone
from sqlalchemy import Column, Integer, BigInteger, String, Float, Date, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    # Changed from Integer to BigInteger to support 64-bit Telegram IDs on PostgreSQL
    id = Column(BigInteger, primary_key=True)  # Telegram user ID
    username = Column(String, nullable=True)
    joined_at = Column(DateTime, default=_utc_now_naive)

    wake_time = Column(String, default="08:00")  # HH:MM, 24-hour
    sleep_time = Column(String, default="23:00")  # HH:MM, 24-hour
    timezone = Column(String, default="UTC")  # tz database name, e.g. "Europe/London"
    language = Column(String, default="en")
    reminder_frequency = Column(Integer, default=3)  # reminders per day
    notification_style = Column(String, default="Standard")  # Standard, Motivational, Direct
    motivation_intensity = Column(String, default="Medium")  # Low, Medium, High
    daily_summary_enabled = Column(Boolean, default=True)
    weekly_summary_enabled = Column(Boolean, default=True)
    theme = Column(String, default="Emoji")  # Emoji, Minimalist

    last_reminder_gen_date = Column(Date, nullable=True)
    last_daily_summary_date = Column(Date, nullable=True)
    last_weekly_summary_date = Column(Date, nullable=True)

    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    reminder_histories = relationship("ReminderHistory", back_populates="user", cascade="all, delete-orphan")
    streak = relationship("Streak", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Changed foreign key to BigInteger to match users.id
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    course_name = Column(String, nullable=True)
    type = Column(String, nullable=False)  # Book, PDF, Slides, Notes, Videos
    unit = Column(String, nullable=False)  # Pages, Slides, Chapters, Lessons, Hours
    total_amount = Column(Float, nullable=False)
    completed_amount = Column(Float, default=0.0)
    deadline = Column(Date, nullable=False)
    daily_study_hours = Column(Float, default=1.0)
    importance = Column(String, default="Medium")  # Low, Medium, High
    difficulty = Column(String, default="Medium")  # Easy, Medium, Hard
    notes = Column(String, nullable=True)
    status = Column(String, default="Active")  # Active, Paused, Completed, Archived
    created_at = Column(DateTime, default=_utc_now_naive)

    user = relationship("User", back_populates="projects")
    progress_logs = relationship("ProgressLog", back_populates="project", cascade="all, delete-orphan")


class ProgressLog(Base):
    __tablename__ = "progress_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    amount_completed = Column(Float, nullable=False)
    logged_at = Column(Date, default=date.today)

    project = relationship("Project", back_populates="progress_logs")


class ReminderHistory(Base):
    __tablename__ = "reminder_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Changed foreign key to BigInteger to match users.id
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    scheduled_for = Column(DateTime, nullable=False)  # naive UTC
    sent_at = Column(DateTime, nullable=True)
    status = Column(String, default="Scheduled")  # Scheduled, Sent, Missed

    user = relationship("User", back_populates="reminder_histories")


class Streak(Base):
    __tablename__ = "streaks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Changed foreign key to BigInteger to match users.id
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    last_activity_date = Column(Date, nullable=True)

    user = relationship("User", back_populates="streak")