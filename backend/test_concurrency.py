"""
Concurrency smoke test: verify that multiple concurrent DB sessions can
read/write without blocking each other.

Uses an in-memory SQLite + aiosqlite DB (no PostgreSQL needed).
"""
import asyncio
import time
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, text

# Import models so Base.metadata is populated
from models.rfp import RFP
from models.feedback import Feedback
from models.knowledge_document import KnowledgeDocument
from database import Base

DB_URL = "sqlite+aiosqlite:///:memory:?check_same_thread=False"

engine = create_async_engine(DB_URL, echo=False)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession,
                                   autocommit=False, autoflush=False,
                                   expire_on_commit=False)


async def setup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def worker(worker_id: int, results: list):
    """Each worker creates an RFP, commits, then reads it back."""
    async with SessionLocal() as db:
        rfp = RFP(
            id=uuid.uuid4().hex,
            filename=f"rfp_{worker_id}.pdf",
            pipeline_status="processing",
        )
        db.add(rfp)
        await db.commit()
        await db.refresh(rfp)

        result = await db.execute(select(RFP).where(RFP.id == rfp.id))
        fetched = result.scalar_one_or_none()
        assert fetched is not None, f"Worker {worker_id}: RFP not found after commit"
        assert fetched.filename == f"rfp_{worker_id}.pdf"
        results.append(worker_id)


async def main():
    await setup()

    N = 20
    results = []
    start = time.perf_counter()

    # Launch N workers concurrently
    await asyncio.gather(*[worker(i, results) for i in range(N)])

    elapsed_ms = round((time.perf_counter() - start) * 1000)
    assert len(results) == N, f"Expected {N} results, got {len(results)}"

    # Verify all N records are in the DB
    async with SessionLocal() as db:
        result = await db.execute(select(RFP))
        all_rfps = result.scalars().all()
    assert len(all_rfps) == N, f"Expected {N} RFPs in DB, got {len(all_rfps)}"

    print(f"PASS: {N} concurrent workers completed without errors in {elapsed_ms} ms")
    print(f"      All {N} records persisted correctly")


asyncio.run(main())
