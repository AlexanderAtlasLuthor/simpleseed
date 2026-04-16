from sqlalchemy import Column, String, Integer, Text, DateTime
from sqlalchemy.sql import func
from database import Base


class Feedback(Base):
    """
    Persists real-world outcomes (won/lost/no_bid) linked to a prior analysis.

    rfp_id is nullable so feedback survives RFP record deletion.
    Snapshot columns capture the state that was in place when the outcome was recorded,
    making historical queries stable even if the source RFP row is later removed.
    """
    __tablename__ = "feedback"

    id                   = Column(String,   primary_key=True)
    org_id               = Column(String,   nullable=True, index=True)  # organisation scope
    rfp_id               = Column(String,   nullable=True, index=True)  # FK to rfps.id, nullable for resilience
    outcome              = Column(String,   nullable=False)              # "won" | "lost" | "no_bid"
    result_date          = Column(String,   nullable=False)              # ISO date string "YYYY-MM-DD"
    notes                = Column(Text,     nullable=True)

    # Snapshot of the analysis at the time feedback was recorded
    original_score       = Column(Integer,  nullable=True)
    original_decision    = Column(String,   nullable=True)              # "BID" | "NO BID"
    industry             = Column(String,   nullable=True)
    strategic_fit_overall = Column(String,  nullable=True)              # "high" | "medium" | "low" | None
    risk_count           = Column(Integer,  nullable=True)
    risk_summary         = Column(Text,     nullable=True)              # JSON list of risk titles

    created_at           = Column(DateTime, server_default=func.now())
