"""
Tests for tracking & observability — feedback, usage recording, and summary metrics.

Run with: pytest backend/tests/test_tracking.py -v
Requires:  pip install pytest

All tests use an in-memory SQLite DB — no external dependencies needed.
"""
import sys
import os

# Make the backend directory importable without installing as a package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# database.Base must be imported BEFORE models so metadata is registered.
from database import Base

from models.rfp import RFP
from models.feedback import Feedback
from models.llm_usage import LLMUsage
from models.pipeline_run import PipelineRun
from services.feedback import (
    VALID_OUTCOMES,
    get_feedback_summary,
    record_feedback,
    upsert_feedback,
)
from services.observability import estimate_cost, MODEL_PRICING


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    """Fresh in-memory SQLite session per test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def rfp(db):
    """Minimal RFP fixture with a known score and decision."""
    r = RFP(
        id="rfp-001",
        filename="test.pdf",
        original_text="test",
        score=72,
        decision="BID",
        industry="technology",
        pipeline_status="completed",
        completed_steps='["requirement_extraction","proposal_generation","bid_scoring"]',
        score_breakdown="{}",
        reasoning="test",
        requirements="{}",
        risks="[]",
        strategic_fit='{"status":"unknown"}',
        knowledge_refs="[]",
        grounding_report="{}",
    )
    db.add(r)
    db.commit()
    return r


# ── Feedback creation ─────────────────────────────────────────────────────────

class TestRecordFeedback:
    def test_creates_row(self, db, rfp):
        fb = record_feedback(db, rfp.id, "won", None, None)
        assert fb.id is not None
        assert fb.rfp_id == rfp.id
        assert fb.outcome == "won"
        # Snapshot captured from RFP
        assert fb.original_score == 72
        assert fb.original_decision == "BID"
        assert fb.industry == "technology"

    def test_defaults_result_date_to_today(self, db, rfp):
        from datetime import date
        fb = record_feedback(db, rfp.id, "lost", None, None)
        assert fb.result_date == date.today().isoformat()

    def test_invalid_outcome_raises(self, db, rfp):
        with pytest.raises(ValueError, match="Invalid outcome"):
            record_feedback(db, rfp.id, "maybe", None, None)

    def test_was_correct_and_comment_stored(self, db, rfp):
        fb = record_feedback(
            db, rfp.id, "won", None, None,
            was_correct=True,
            comment="Great recommendation",
        )
        assert fb.was_correct is True
        assert fb.comment == "Great recommendation"

    def test_was_correct_false_stored(self, db, rfp):
        fb = record_feedback(db, rfp.id, "lost", None, None, was_correct=False)
        assert fb.was_correct is False

    def test_all_valid_outcomes_accepted(self, db, rfp):
        for outcome in VALID_OUTCOMES:
            fb = record_feedback(db, rfp.id, outcome, None, None)
            assert fb.outcome == outcome

    def test_not_pursued_accepted(self, db, rfp):
        fb = record_feedback(db, rfp.id, "not_pursued", None, None)
        assert fb.outcome == "not_pursued"


# ── Upsert feedback ───────────────────────────────────────────────────────────

class TestUpsertFeedback:
    def test_creates_new_row(self, db, rfp):
        fb = upsert_feedback(db, rfp.id, was_correct=True)
        assert fb.was_correct is True
        assert db.query(Feedback).count() == 1

    def test_updates_existing_row(self, db, rfp):
        upsert_feedback(db, rfp.id, was_correct=True)
        upsert_feedback(db, rfp.id, was_correct=False, outcome="lost")
        rows = db.query(Feedback).all()
        assert len(rows) == 1
        assert rows[0].was_correct is False
        assert rows[0].outcome == "lost"

    def test_partial_update_preserves_existing(self, db, rfp):
        upsert_feedback(db, rfp.id, was_correct=True, outcome="won")
        upsert_feedback(db, rfp.id, comment="Updated comment")
        fb = db.query(Feedback).first()
        assert fb.was_correct is True        # preserved
        assert fb.outcome == "won"           # preserved
        assert fb.comment == "Updated comment"

    def test_invalid_outcome_raises(self, db, rfp):
        with pytest.raises(ValueError, match="Invalid outcome"):
            upsert_feedback(db, rfp.id, outcome="bad")

    def test_none_values_do_not_overwrite(self, db, rfp):
        upsert_feedback(db, rfp.id, was_correct=True)
        upsert_feedback(db, rfp.id, was_correct=None)  # None → no overwrite
        fb = db.query(Feedback).first()
        assert fb.was_correct is True  # unchanged


# ── Feedback summary ──────────────────────────────────────────────────────────

class TestFeedbackSummary:
    def test_empty_returns_zero_counts(self, db):
        s = get_feedback_summary(db)
        assert s["total_feedback_records"] == 0
        assert s["win_rate_overall"] is None
        assert s["correct_rate"] is None
        assert s["override_rate"] is None

    def test_win_rate_computed(self, db, rfp):
        record_feedback(db, rfp.id, "won",  None, None)
        record_feedback(db, rfp.id, "won",  None, None)
        record_feedback(db, rfp.id, "lost", None, None)
        s = get_feedback_summary(db)
        assert s["wins"] == 2
        assert s["losses"] == 1
        assert abs(s["win_rate_overall"] - 0.667) < 0.01

    def test_correct_rate_computed(self, db, rfp):
        record_feedback(db, rfp.id, "won", None, None, was_correct=True)
        record_feedback(db, rfp.id, "won", None, None, was_correct=True)
        record_feedback(db, rfp.id, "lost", None, None, was_correct=False)
        s = get_feedback_summary(db)
        assert s["correct_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert s["override_rate"] == pytest.approx(1 / 3, abs=0.01)

    def test_override_rate_is_one_when_all_incorrect(self, db, rfp):
        record_feedback(db, rfp.id, "lost", None, None, was_correct=False)
        record_feedback(db, rfp.id, "lost", None, None, was_correct=False)
        s = get_feedback_summary(db)
        assert s["override_rate"] == 1.0
        assert s["correct_rate"] == 0.0

    def test_no_bids_excluded_from_win_rate(self, db, rfp):
        record_feedback(db, rfp.id, "no_bid", None, None)
        record_feedback(db, rfp.id, "not_pursued", None, None)
        record_feedback(db, rfp.id, "won", None, None)
        s = get_feedback_summary(db)
        # win rate uses only won+lost rows → 1 won / 1 total = 1.0
        assert s["win_rate_overall"] == 1.0


# ── Ownership: feedback on unknown RFP ───────────────────────────────────────

class TestOwnershipAndResilience:
    def test_feedback_without_rfp_row(self, db):
        """Should create a row with null snapshot fields, not raise."""
        fb = record_feedback(db, "nonexistent-id", "lost", None, None)
        assert fb.rfp_id == "nonexistent-id"
        assert fb.original_score is None
        assert fb.original_decision is None


# ── LLM usage model ───────────────────────────────────────────────────────────

class TestLLMUsage:
    def test_row_persists(self, db):
        row = LLMUsage(
            id="u-001",
            request_id="req-abc",
            model="claude-haiku-4-5-20251001",
            service="extractor",
            input_tokens=500,
            output_tokens=200,
            total_tokens=700,
            estimated_cost=0.00124,
        )
        db.add(row)
        db.commit()
        fetched = db.query(LLMUsage).filter_by(id="u-001").first()
        assert fetched.service == "extractor"
        assert fetched.total_tokens == 700

    def test_estimate_cost_haiku(self):
        cost = estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 0)
        assert abs(cost - 0.80) < 0.0001

    def test_estimate_cost_output_tokens(self):
        cost = estimate_cost("claude-haiku-4-5-20251001", 0, 1_000_000)
        assert abs(cost - 4.00) < 0.0001

    def test_estimate_cost_unknown_model_uses_default(self):
        cost = estimate_cost("unknown-model-xyz", 1_000_000, 0)
        # Falls back to default pricing (same as haiku)
        assert cost > 0


# ── PipelineRun model ─────────────────────────────────────────────────────────

class TestPipelineRun:
    def test_row_persists(self, db):
        run = PipelineRun(
            id="run-001",
            request_id="req-xyz",
            rfp_id="rfp-001",
            status="success",
            total_duration_ms=3412,
        )
        db.add(run)
        db.commit()
        fetched = db.query(PipelineRun).filter_by(id="run-001").first()
        assert fetched.status == "success"
        assert fetched.total_duration_ms == 3412
        assert fetched.request_id == "req-xyz"
