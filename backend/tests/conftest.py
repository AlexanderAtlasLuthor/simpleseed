"""
Shared fixtures for the SimpleSeed test suite.

Environment variables are set here, BEFORE any app module is imported,
so that settings.py and database.py read the correct test values.
"""
import os
import sys
from unittest.mock import MagicMock

# ── Must come before any app import ───────────────────────────────────────
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-placeholder")
os.environ.setdefault("LLM_MODEL", "claude-haiku-4-5-20251001")
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["APP_ENV"] = "test"

# pdfplumber → pdfminer → cryptography has a broken native extension in this
# environment. Stub it out at the sys.modules level so the import never fires.
sys.modules.setdefault("pdfplumber", MagicMock())

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── stdlib / third-party ───────────────────────────────────────────────────
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


# ── Helpers ────────────────────────────────────────────────────────────────

def make_llm_response(text: str) -> MagicMock:
    """Return a fake anthropic.types.Message with a single text content block."""
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


# ── DB fixtures ────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_engine():
    """
    Fresh in-memory SQLite engine per test.
    StaticPool ensures all connections see the same in-memory DB.
    """
    from database import Base
    import models.rfp              # noqa: F401 — registers with Base.metadata
    import models.feedback         # noqa: F401
    import models.knowledge_document  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Async session bound to the test engine, rolled back after each test."""
    factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session
        await session.rollback()


# ── HTTP client fixture ────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def http_client(db_engine):
    """
    AsyncClient wired to the real FastAPI app with:
      - get_db dependency overridden to use the in-memory test engine
      - startup init_db patched to a no-op (tables already created by db_engine)
    """
    from database import get_db
    from main import app

    factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    with patch("main.init_db", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client

    app.dependency_overrides.clear()
