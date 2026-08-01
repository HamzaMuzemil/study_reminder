# database.py
import logging
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from config import Config

logger = logging.getLogger(__name__)

# Configure connection arguments dynamically based on database type
connect_args = {}
if Config.DATABASE_URL.startswith("postgresql"):
    # Disables prepared statement caching to support transaction-mode connection poolers (like Supavisor)
    connect_args["statement_cache_size"] = 0

engine = create_async_engine(
    Config.DATABASE_URL,
    connect_args=connect_args,
    echo=False
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Runs once per new database connection.
    
    Only applies WAL mode and foreign key enforcement if the active 
    connection is actually using SQLite to avoid aborting transactions on PostgreSQL.
    """
    if "sqlite" in engine.url.drivername:
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        except Exception:
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