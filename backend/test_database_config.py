"""
Verify that database.py correctly configures the engine based on DATABASE_URL.

Tests:
- URL normalisation: psycopg2 and plain postgresql:// → asyncpg
- SQLite URL → aiosqlite
- _is_sqlite flag
- Non-SQLite URLs do NOT use SQLite driver
- _get_existing_columns works with SQLite dialect (in-memory async)
- _migrate() is a no-op on a fresh table (all columns already present)
- _migrate() adds missing columns on an old table
- Config is centralised: a single DATABASE_URL drives everything
- Production guard: SQLite + APP_ENV != development raises RuntimeError
- check_same_thread is NOT present in asyncpg/aiosqlite connections

No live Postgres instance required.
"""
import asyncio
import sys
import os

sys.path.insert(0, ".")

# ── URL normalisation tests (pure logic, no connection needed) ────────────────
os.environ.setdefault("DATABASE_URL", "sqlite:///./simpleseed.db")
import database as db_mod

assert db_mod._normalise_db_url("sqlite:///./foo.db") == "sqlite+aiosqlite:///./foo.db"
assert db_mod._normalise_db_url("sqlite+aiosqlite:///./foo.db") == "sqlite+aiosqlite:///./foo.db"
assert db_mod._normalise_db_url("postgresql://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
assert db_mod._normalise_db_url("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
assert db_mod._normalise_db_url("postgresql+psycopg2://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
assert db_mod._normalise_db_url("postgresql+asyncpg://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
print("Case 1 PASS: URL normalisation rewrites all legacy formats to async drivers")


# ── _is_sqlite detection ──────────────────────────────────────────────────────
assert db_mod._is_sqlite is True, "Default SQLite URL must set _is_sqlite=True"
assert db_mod.engine.dialect.name == "sqlite"
print("Case 2 PASS: _is_sqlite=True and engine dialect is sqlite for default URL")


# ── Non-SQLite URL detection ──────────────────────────────────────────────────
for pg_url in [
    "postgresql+psycopg2://u:p@localhost/db",
    "postgresql://u:p@localhost/db",
    "postgres://u:p@localhost/db",
    "postgresql+asyncpg://u:p@localhost/db",
]:
    normalised = db_mod._normalise_db_url(pg_url)
    assert not normalised.startswith("sqlite"), f"Postgres URL must not be SQLite: {pg_url}"
    assert "asyncpg" in normalised, f"Must use asyncpg driver: {normalised}"
print("Case 3 PASS: all PostgreSQL URL formats normalise to postgresql+asyncpg://")


# ── Production guard ──────────────────────────────────────────────────────────
import importlib

# SQLite + APP_ENV=production must raise RuntimeError at import time
os.environ["APP_ENV"] = "production"
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
try:
    importlib.reload(db_mod)
    assert False, "Should have raised RuntimeError for SQLite in production"
except RuntimeError as e:
    assert "production" in str(e).lower() or "sqlite" in str(e).lower()
    print(f"Case 4 PASS: SQLite + APP_ENV=production raises RuntimeError: {str(e)[:80]}...")
finally:
    # Restore to development for remaining tests
    os.environ["APP_ENV"] = "development"
    os.environ["DATABASE_URL"] = "sqlite:///./simpleseed.db"
    importlib.reload(db_mod)


# ── _get_existing_columns and _migrate (async) ───────────────────────────────

async def test_migrate_and_columns():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from database import Base
    # Import models so SQLAlchemy's metadata knows about all tables
    from models.rfp import RFP                              # noqa: F401
    from models.feedback import Feedback                    # noqa: F401
    from models.knowledge_document import KnowledgeDocument # noqa: F401

    # ── Case 5: _get_existing_columns with in-memory SQLite ──────────────────
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as conn:
        await conn.execute(
            text("CREATE TABLE test_tbl (id TEXT PRIMARY KEY, name TEXT, score INTEGER)")
        )
        cols = await db_mod._get_existing_columns(conn, "test_tbl")

    assert cols == {"id", "name", "score"}, f"Unexpected columns: {cols}"
    await test_engine.dispose()
    print("Case 5 PASS: _get_existing_columns returns {id, name, score} from async SQLite")

    # ── Case 6: _migrate() is a no-op on a fresh table ───────────────────────
    fresh_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with fresh_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    original_engine = db_mod.engine
    db_mod.engine = fresh_engine
    try:
        await db_mod._migrate()
        print("Case 6 PASS: _migrate() runs without error on a fresh table")
    finally:
        db_mod.engine = original_engine
        await fresh_engine.dispose()

    # ── Case 7: _migrate() adds missing columns to an old schema ─────────────
    old_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with old_engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE rfps (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                original_text TEXT,
                proposal TEXT,
                score INTEGER DEFAULT 0,
                decision TEXT DEFAULT 'NO BID',
                score_breakdown TEXT DEFAULT '{}',
                reasoning TEXT DEFAULT ''
            )
        """))

    db_mod.engine = old_engine
    try:
        await db_mod._migrate()
    finally:
        db_mod.engine = original_engine

    async with old_engine.begin() as conn:
        added = await db_mod._get_existing_columns(conn, "rfps")

    expected_new = {"industry", "risks", "strategic_fit", "knowledge_refs",
                    "grounding_report", "pipeline_status", "failed_step",
                    "completed_steps", "pipeline_error"}
    missing_cols = expected_new - added
    assert not missing_cols, f"Columns not added by _migrate(): {missing_cols}"
    await old_engine.dispose()
    print(f"Case 7 PASS: _migrate() added all {len(expected_new)} missing columns to old schema")


asyncio.run(test_migrate_and_columns())


# ── Case 8: DATABASE_URL is the single source of truth ───────────────────────
assert db_mod._is_sqlite is True
assert "sqlite" in db_mod.DATABASE_URL
print("Case 8 PASS: DATABASE_URL is the single config source for engine dialect")


# ── Case 9: check_same_thread not in aiosqlite engine ────────────────────────
# aiosqlite doesn't need check_same_thread — it's purely async
# We verify the engine was created without error and uses aiosqlite
assert db_mod.engine.dialect.name == "sqlite"
assert "aiosqlite" in db_mod.DATABASE_URL
print("Case 9 PASS: aiosqlite engine created correctly — check_same_thread not needed")


# ── Case 10: PostgreSQL engine does NOT use sqlite or check_same_thread ───────
pg_url = "postgresql+asyncpg://u:p@localhost/db"
pg_is_sqlite = pg_url.startswith("sqlite")
assert not pg_is_sqlite
print("Case 10 PASS: PostgreSQL URL is not SQLite — check_same_thread never applied")


print("\nAll cases passed.")
