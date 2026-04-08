import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

# ── Database URL ──────────────────────────────────────────────────────────────
# Development default: SQLite (zero-config, single-file, dev only)
# Production: set DATABASE_URL to a PostgreSQL URL, e.g.:
#   postgresql+psycopg2://user:pass@db:5432/simpleseed
#
# WARNING: SQLite with check_same_thread=False is NOT safe for concurrent
# production traffic.  It is provided for local development only.
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./simpleseed.db")

_is_sqlite = DATABASE_URL.startswith("sqlite")

# ── Engine ────────────────────────────────────────────────────────────────────
if _is_sqlite:
    # SQLite: check_same_thread=False is required because FastAPI's thread pool
    # may dispatch requests to different threads than the one that opened the
    # connection.  This is acceptable for development but is NOT production-safe
    # under concurrent write load — use PostgreSQL for production.
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    # PostgreSQL (or any other production RDBMS):
    # - pool_pre_ping: validate each connection before handing it to a request;
    #   detects stale connections without raising mid-request errors
    # - pool_recycle: recycle connections after 5 min to survive server-side
    #   idle-connection timeouts (common on managed Postgres like RDS/Supabase)
    # - pool_size / max_overflow: allows up to 15 concurrent DB connections,
    #   which covers typical MVP load without exhausting Postgres's default
    #   max_connections=100
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=300,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# ── Public API ────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create tables and run lightweight column migrations."""
    from models.rfp import RFP                              # noqa: F401
    from models.feedback import Feedback                    # noqa: F401
    from models.knowledge_document import KnowledgeDocument # noqa: F401
    from models.user import User                            # noqa: F401  ← auth
    Base.metadata.create_all(bind=engine)
    _migrate()


def get_db():
    """FastAPI dependency: yields a DB session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_existing_columns(conn, table_name: str) -> set:
    """
    Return the set of existing column names for table_name.
    Uses dialect-specific introspection so the same code works on both
    SQLite (PRAGMA) and PostgreSQL (information_schema).
    """
    dialect = conn.dialect.name
    if dialect == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table_name})"))
        return {row[1] for row in rows}
    # PostgreSQL and any SQL-99-compliant RDBMS
    rows = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table_name},
    )
    return {row[0] for row in rows}


def _table_exists(conn, table_name: str) -> bool:
    """Return True if table_name exists in the database."""
    dialect = conn.dialect.name
    if dialect == "sqlite":
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
            {"t": table_name},
        )
        return rows.fetchone() is not None
    rows = conn.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table_name},
    )
    return rows.fetchone() is not None


def _migrate() -> None:
    """
    Add columns introduced after the initial schema without dropping data.

    For a fresh install, create_all() already creates every column declared
    in the models, so _migrate() is effectively a no-op.

    For existing deployments (SQLite dev DBs or older Postgres installs),
    this adds only the columns that are genuinely absent.

    NOTE: This is a minimal migration strategy suitable for an MVP.
    For production-grade schema evolution use Alembic.
    """
    with engine.connect() as conn:
        # ── rfps table ────────────────────────────────────────────────────────
        if _table_exists(conn, "rfps"):
            existing_rfp = _get_existing_columns(conn, "rfps")

            rfp_columns: dict[str, str] = {
                "industry":         "TEXT DEFAULT 'general'",
                "risks":            "TEXT DEFAULT '[]'",
                "strategic_fit":    "TEXT DEFAULT '{}'",
                "knowledge_refs":   "TEXT DEFAULT '[]'",
                "grounding_report": "TEXT DEFAULT '{}'",
                "pipeline_status":  "TEXT DEFAULT 'completed'",
                "failed_step":      "TEXT",
                "completed_steps":  "TEXT DEFAULT '[]'",
                "pipeline_error":   "TEXT",
                # user_id is nullable so pre-auth records are preserved
                "user_id":          "TEXT",
            }

            for col, definition in rfp_columns.items():
                if col not in existing_rfp:
                    conn.execute(text(f"ALTER TABLE rfps ADD COLUMN {col} {definition}"))

        conn.commit()
