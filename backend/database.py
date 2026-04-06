"""
Database configuration for SimpleSeed.

Engine selection
----------------
The engine (and its async driver) is chosen automatically based on DATABASE_URL:

  SQLite (development / test only):
    sqlite:///./simpleseed.db        → auto-rewritten to sqlite+aiosqlite:///./simpleseed.db

  PostgreSQL (production):
    postgresql+asyncpg://user:pass@host:5432/db   (native async URL — preferred)
    postgresql+psycopg2://...                      → auto-rewritten to asyncpg
    postgresql://... or postgres://...             → auto-rewritten to asyncpg

The rewrite is transparent: existing .env files and docker-compose configs that
use psycopg2 or plain postgresql:// URLs continue to work without any changes.

Production guard
----------------
If DATABASE_URL resolves to SQLite and APP_ENV is not "development" or "test",
the process raises RuntimeError at import time, preventing a misconfigured
production deployment from ever starting.

Session management
------------------
Every HTTP request gets its own AsyncSession via the get_db() FastAPI dependency.
Sessions are never shared between requests.  expire_on_commit=False ensures that
ORM attributes remain accessible after a commit without a new round-trip query.

Connection pool (PostgreSQL only)
----------------------------------
  pool_size=5     — persistent connections kept alive in the pool
  max_overflow=10 — up to 10 extra connections under burst load (total 15 max)
  pool_pre_ping   — validates each connection before use; drops stale ones
  pool_recycle=300 — recycles connections after 5 min to survive idle timeouts
                     common on managed Postgres (RDS, Supabase, Railway, etc.)
"""

import logging
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── URL normalisation ─────────────────────────────────────────────────────────

def _normalise_db_url(url: str) -> str:
    """
    Rewrite legacy sync-driver prefixes to their async equivalents.

    This lets operators keep existing DATABASE_URL values (e.g. psycopg2 or plain
    postgresql://) without any .env changes.

    Mapping:
      postgres://...              → postgresql+asyncpg://...
      postgresql://...            → postgresql+asyncpg://...
      postgresql+psycopg2://...   → postgresql+asyncpg://...
      sqlite:///...               → sqlite+aiosqlite:///...
      (already async)             → returned unchanged
    """
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql+asyncpg://" + url[len("postgresql+psycopg2://"):]
    if url.startswith("sqlite:///"):
        return "sqlite+aiosqlite:///" + url[len("sqlite:///"):]
    # Already uses an explicit async driver (e.g. postgresql+asyncpg://...) — pass through
    return url


# ── Database URL ──────────────────────────────────────────────────────────────

_RAW_DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./simpleseed.db")
DATABASE_URL: str = _normalise_db_url(_RAW_DATABASE_URL)
_is_sqlite: bool = DATABASE_URL.startswith("sqlite")

# ── Production guard ──────────────────────────────────────────────────────────

APP_ENV: str = os.getenv("APP_ENV", "development")

if _is_sqlite and APP_ENV not in ("development", "test"):
    raise RuntimeError(
        f"SQLite is not supported in '{APP_ENV}' environment.  "
        "Set DATABASE_URL to a PostgreSQL connection string, e.g.:\n"
        "  DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname\n"
        "SQLite is only permitted when APP_ENV=development or APP_ENV=test."
    )

# ── Async engine ──────────────────────────────────────────────────────────────

if _is_sqlite:
    # aiosqlite: zero-config async SQLite for local development.
    # No connect_args required — aiosqlite's async model doesn't need
    # check_same_thread (that restriction only applies to the sync driver).
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
    )
    logger.debug("DB engine: SQLite (development) url=%s", DATABASE_URL)
else:
    # asyncpg: production-grade async PostgreSQL driver.
    # pool_size + max_overflow allow up to 15 concurrent DB connections,
    # sufficient for typical MVP load without exhausting Postgres defaults.
    engine = create_async_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=300,
        echo=False,
    )
    # Log only the host/db portion (never credentials) for safety
    safe_url = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    logger.debug("DB engine: PostgreSQL (async) host/db=%s", safe_url)

# ── Session factory ───────────────────────────────────────────────────────────

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    # expire_on_commit=False: keep ORM attributes accessible after commit
    # without issuing an implicit SELECT.  Important for async contexts where
    # an accidental attribute access after commit would trigger a lazy-load
    # error (MissingGreenlet) rather than a transparent round-trip.
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


# ── Public API ────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create tables and run lightweight column migrations."""
    from models.rfp import RFP                              # noqa: F401
    from models.feedback import Feedback                    # noqa: F401
    from models.knowledge_document import KnowledgeDocument # noqa: F401

    async with engine.begin() as conn:
        # run_sync lets us call synchronous DDL helpers from an async context
        await conn.run_sync(Base.metadata.create_all)

    await _migrate()


async def get_db():
    """
    FastAPI dependency: yields a dedicated AsyncSession for one request.

    Each request gets its own session — sessions are never shared.
    The session is closed automatically when the request finishes (or errors).
    """
    async with SessionLocal() as session:
        yield session


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _get_existing_columns(conn, table_name: str) -> set:
    """
    Return the set of existing column names for table_name.
    Works on SQLite (PRAGMA) and PostgreSQL (information_schema).
    """
    dialect = conn.dialect.name
    if dialect == "sqlite":
        rows = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        return {row[1] for row in rows}
    # PostgreSQL / any SQL-99-compliant RDBMS
    rows = await conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table_name},
    )
    return {row[0] for row in rows}


async def _migrate() -> None:
    """
    Add columns introduced after the initial schema without dropping data.

    For a fresh install, create_all() already creates every column declared
    in the models so _migrate() is a no-op.

    For existing deployments, this adds only genuinely absent columns.

    NOTE: Suitable for MVP.  Use Alembic for production-grade schema evolution.
    """
    async with engine.begin() as conn:
        existing = await _get_existing_columns(conn, "rfps")

        new_columns: dict[str, str] = {
            "industry":         "TEXT DEFAULT 'general'",
            "risks":            "TEXT DEFAULT '[]'",
            "strategic_fit":    "TEXT DEFAULT '{}'",
            "knowledge_refs":   "TEXT DEFAULT '[]'",
            "grounding_report": "TEXT DEFAULT '{}'",
            "pipeline_status":  "TEXT DEFAULT 'completed'",
            "failed_step":      "TEXT",
            "completed_steps":  "TEXT DEFAULT '[]'",
            "pipeline_error":   "TEXT",
        }

        for col, definition in new_columns.items():
            if col not in existing:
                await conn.execute(
                    text(f"ALTER TABLE rfps ADD COLUMN {col} {definition}")
                )
