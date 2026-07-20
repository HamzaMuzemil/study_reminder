import logging
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from config import Config

logger = logging.getLogger(__name__)

engine = create_async_engine(Config.DATABASE_URL, echo=False)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Runs once per new SQLite connection.

    - WAL mode lets one connection write while others read, instead of
      locking the whole database file on every write. With a Telegram bot,
      that means someone logging progress doesn't get blocked by the
      background scheduler tick (or vice versa).
    - foreign_keys=ON makes SQLite actually enforce the ondelete="CASCADE"
      rules declared in models.py (SQLite ignores them by default).
    """
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        # If DATABASE_URL ever points somewhere non-SQLite, these pragmas
        # simply wouldn't apply -- fail safe rather than crash startup.
        pass


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


async def init_db():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified/created.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}", exc_info=True)
        raise
