from sqlalchemy import Boolean, Column, String, Integer, Text, DateTime
from sqlalchemy.sql import func
from database import Base


class Feedback(Base):
    """
    Persists real-world outcomes and user correctness signals for a prior analysis.

    rfp_id is nullable so feedback survives RFP record deletion.
    Snapshot columns capture the state that was in place when the outcome was recorded,
    making historical queries stable even if the source RFP row is later removed.

    was_correct: user's subjective assessment of the AI recommendation quality.
    comment: optional free-text from the user (replaces older "notes" field but notes
             is kept for backwards compatibility).
    """
    __tablename__ = "feedback"

    id                    = Column(String,   primary_key=True)
    rfp_id                = Column(String,   nullable=True, index=True)   # FK to rfps.id, nullable for resilience
    outcome               = Column(String,   nullable=True)               # "won" | "lost" | "no_bid" | "not_pursued"
    result_date           = Column(String,   nullable=True)               # ISO date string "YYYY-MM-DD"
    notes                 = Column(Text,     nullable=True)               # legacy free-text field
    was_correct           = Column(Boolean,  nullable=True)               # user: was the AI recommendation correct?
    comment               = Column(Text,     nullable=True)               # structured user comment

    # Snapshot of the analysis at the time feedback was recorded
    original_score        = Column(Integer,  nullable=True)
    original_decision     = Column(String,   nullable=True)               # "BID" | "NO BID"
    industry              = Column(String,   nullable=True)
    strategic_fit_overall = Column(String,   nullable=True)               # "high" | "medium" | "low" | None
    risk_count            = Column(Integer,  nullable=True)
    risk_summary          = Column(Text,     nullable=True)               # JSON list of risk titles

    created_at            = Column(DateTime, server_default=func.now())
