"""
Verify feedback recording, aggregation, and calibration logic.
Uses an in-memory async SQLite DB — no LLM calls, no external services.
"""
import asyncio
import sys
import json
from datetime import date

sys.path.insert(0, ".")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

# Create a fresh in-memory async DB for this test run
from database import Base
from models.rfp import RFP
from models.feedback import Feedback

from services.feedback import (
    record_feedback, get_feedback_for_rfp, get_all_feedback,
    get_feedback_summary, _win_rate, _compute_calibration,
    VALID_OUTCOMES,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def make_rfp(db: AsyncSession, score=72, decision="BID", industry="healthcare",
                   fit_overall="high",
                   risks_json='[{"title":"Tight deadline"},{"title":"HIPAA cert required"}]'):
    import uuid
    rfp = RFP(
        id=str(uuid.uuid4()),
        filename="test.pdf",
        score=score,
        decision=decision,
        industry=industry,
        risks=risks_json,
        strategic_fit=json.dumps({"overall": fit_overall, "status": "evaluated"}),
    )
    db.add(rfp)
    await db.commit()
    await db.refresh(rfp)
    return rfp


def make_feedback_row(outcome, score, industry="healthcare", fit="high"):
    """Simulate a Feedback ORM object without touching the DB."""
    class _F:
        pass
    f = _F()
    f.outcome = outcome
    f.original_score = score
    f.industry = industry
    f.strategic_fit_overall = fit
    f.risk_count = 1
    f.risk_summary = "[]"
    return f


# ── Main async test runner ───────────────────────────────────────────────────

async def main():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession,
                                  autocommit=False, autoflush=False,
                                  expire_on_commit=False)

    async with Session() as db:

        # ── Case 1: valid outcomes accepted ──────────────────────────────────
        rfp = await make_rfp(db, score=72, decision="BID", industry="healthcare")
        fb = await record_feedback(db, rfp.id, "won", "2026-03-15", "Strong past performance")
        assert fb.outcome == "won"
        assert fb.rfp_id  == rfp.id
        assert fb.original_score == 72
        assert fb.original_decision == "BID"
        assert fb.industry == "healthcare"
        assert fb.strategic_fit_overall == "high"
        assert fb.risk_count == 2
        assert fb.result_date == "2026-03-15"
        assert fb.notes == "Strong past performance"
        risk_titles = json.loads(fb.risk_summary)
        assert "Tight deadline" in risk_titles
        print(f"Case 1 PASS: 'won' feedback recorded with full snapshot "
              f"(score={fb.original_score}, risks={risk_titles})")

        # ── Case 2: lost feedback linked to different RFP ─────────────────────
        rfp2 = await make_rfp(db, score=58, decision="NO BID", industry="technology",
                               fit_overall="low")
        fb2 = await record_feedback(db, rfp2.id, "lost", "2026-03-20", None)
        assert fb2.outcome == "lost"
        assert fb2.original_score == 58
        assert fb2.industry == "technology"
        assert fb2.strategic_fit_overall == "low"
        print(f"Case 2 PASS: 'lost' feedback for score=58, industry=technology")

        # ── Case 3: no_bid feedback ───────────────────────────────────────────
        rfp3 = await make_rfp(db, score=45, decision="NO BID", industry="construction",
                               fit_overall="low")
        fb3 = await record_feedback(db, rfp3.id, "no_bid", None, "Decided not to bid")
        assert fb3.outcome == "no_bid"
        assert fb3.result_date == date.today().isoformat()
        print(f"Case 3 PASS: 'no_bid' with default today date = {fb3.result_date}")

        # ── Case 4: invalid outcome → ValueError ──────────────────────────────
        try:
            await record_feedback(db, rfp.id, "maybe", "2026-03-01", None)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "maybe" in str(e)
            assert all(v in str(e) for v in VALID_OUTCOMES)
        print(f"Case 4 PASS: invalid outcome 'maybe' → ValueError with valid options listed")

        # ── Case 5: invalid date → ValueError ────────────────────────────────
        try:
            await record_feedback(db, rfp.id, "won", "not-a-date", None)
            assert False
        except ValueError as e:
            assert "result_date" in str(e)
        print(f"Case 5 PASS: invalid date 'not-a-date' → ValueError")

        # ── Case 6: get_feedback_for_rfp returns correct records ──────────────
        records = await get_feedback_for_rfp(db, rfp.id)
        assert len(records) == 1
        assert records[0]["outcome"] == "won"
        assert records[0]["rfp_id"] == rfp.id
        records2 = await get_feedback_for_rfp(db, rfp2.id)
        assert len(records2) == 1
        assert records2[0]["outcome"] == "lost"
        print(f"Case 6 PASS: get_feedback_for_rfp correctly isolates records per RFP")

        # ── Case 7: get_all_feedback returns all rows ─────────────────────────
        all_fb = await get_all_feedback(db)
        assert len(all_fb) == 3  # won + lost + no_bid
        outcomes = {r["outcome"] for r in all_fb}
        assert outcomes == {"won", "lost", "no_bid"}
        print(f"Case 7 PASS: get_all_feedback returns all 3 records")

        # ── Case 8: _win_rate computation ─────────────────────────────────────
        rows = [make_feedback_row("won",  80)] * 3 + [make_feedback_row("lost", 50)] * 1
        assert _win_rate(rows) == 0.75
        rows_all_loss = [make_feedback_row("lost", 40)] * 4
        assert _win_rate(rows_all_loss) == 0.0
        rows_mixed_nobid = [make_feedback_row("won", 70)] * 2 + [make_feedback_row("no_bid", 55)] * 5
        assert _win_rate(rows_mixed_nobid) == 1.0
        print(f"Case 8 PASS: _win_rate correctly excludes no_bid from denominator")

        # ── Case 9: get_feedback_summary counts ──────────────────────────────
        summary = await get_feedback_summary(db)
        assert summary["total_feedback_records"] == 3
        assert summary["wins"]    == 1
        assert summary["losses"]  == 1
        assert summary["no_bids"] == 1
        print(f"Case 9 PASS: summary counts: won={summary['wins']}, "
              f"lost={summary['losses']}, no_bid={summary['no_bids']}")

        # ── Case 10: score band breakdown present ─────────────────────────────
        bands = summary["win_rate_by_score_band"]
        assert "70-79" in bands, f"Expected 70-79 band, got: {list(bands.keys())}"
        assert bands["70-79"]["win_rate"] == 1.0
        assert "50-59" in bands
        assert bands["50-59"]["win_rate"] == 0.0
        print(f"Case 10 PASS: score bands 70-79 wr=1.0, 50-59 wr=0.0")

        # ── Case 11: calibration insight with insufficient data ───────────────
        # Use a fresh empty session/engine
        engine2 = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine2.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        Session2 = async_sessionmaker(bind=engine2, class_=AsyncSession,
                                       autocommit=False, autoflush=False,
                                       expire_on_commit=False)
        async with Session2() as db2:
            empty_summary = await get_feedback_summary(db2)
        assert empty_summary["calibration_insight"]["status"] == "insufficient_data"
        await engine2.dispose()
        print(f"Case 11 PASS: empty DB → calibration status='insufficient_data'")

        # ── Case 12: calibration — threshold may be too high ──────────────────
        band_rates_high_threshold = {
            "50-59": {"win_rate": 0.60, "count": 5},
            "60-69": {"win_rate": 0.55, "count": 5},
        }
        rows_enough = [make_feedback_row("won", 55)] * 3 + [make_feedback_row("lost", 65)] * 2
        result = _compute_calibration(rows_enough, band_rates_high_threshold)
        assert result["status"] == "threshold_may_be_too_high", f"Got: {result['status']}"
        assert "lower" in result["message"].lower()
        print(f"Case 12 PASS: high below-threshold win rate → 'threshold_may_be_too_high'")

        # ── Case 13: calibration — threshold may be too low ───────────────────
        band_rates_low_threshold = {
            "60-69": {"win_rate": 0.20, "count": 5},
        }
        rows_losses_above = ([make_feedback_row("lost", 65)] * 4
                             + [make_feedback_row("won", 65)] * 1)
        result = _compute_calibration(rows_losses_above, band_rates_low_threshold)
        assert result["status"] == "threshold_may_be_too_low", f"Got: {result['status']}"
        assert (
            "raise" in result["message"].lower()
            or "higher" in result["message"].lower()
            or "raising" in result["message"].lower()
        )
        print(f"Case 13 PASS: low above-threshold win rate → 'threshold_may_be_too_low'")

        # ── Case 14: feedback snapshot survives independently ─────────────────
        fb_result = await db.execute(
            select(Feedback).where(Feedback.rfp_id == rfp.id)
        )
        fb_check = fb_result.scalar_one_or_none()
        assert fb_check.original_score == 72
        assert fb_check.industry == "healthcare"
        assert fb_check.strategic_fit_overall == "high"
        assert fb_check.risk_count == 2
        assert json.loads(fb_check.risk_summary) == ["Tight deadline", "HIPAA cert required"]
        print(f"Case 14 PASS: snapshot fields persisted correctly and queryable independently")

        # ── Case 15: record feedback for non-existent rfp ─────────────────────
        fb_orphan = await record_feedback(
            db, "rfp-that-does-not-exist", "lost", "2026-01-01", "Pre-existing record"
        )
        assert fb_orphan.rfp_id == "rfp-that-does-not-exist"
        assert fb_orphan.original_score is None
        assert fb_orphan.industry is None
        print(f"Case 15 PASS: feedback for missing rfp_id stored with null snapshot fields")

    await engine.dispose()
    print("\nAll cases passed.")


asyncio.run(main())
