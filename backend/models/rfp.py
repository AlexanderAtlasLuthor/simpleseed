from sqlalchemy import Column, ForeignKey, String, Integer, Text, DateTime
from sqlalchemy.sql import func
from database import Base


class RFP(Base):
    __tablename__ = "rfps"

    id = Column(String, primary_key=True)
    # owner — nullable so pre-auth records are preserved and not surfaced to any user
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    filename = Column(String, nullable=False)
    original_text = Column(Text)
    requirements = Column(Text)
    proposal = Column(Text)
    score = Column(Integer, default=0)
    decision = Column(String, default="NO BID")
    score_breakdown = Column(Text, default="{}")
    reasoning = Column(Text, default="")
    industry = Column(String, nullable=True, default="general")
    risks = Column(Text, nullable=True, default="[]")
    strategic_fit = Column(Text, nullable=True, default="{}")
    knowledge_refs = Column(Text, nullable=True, default="[]")
    grounding_report = Column(Text, nullable=True, default="{}")
    pipeline_status = Column(String, default="completed")   # processing | completed | partial_failure
    failed_step = Column(String, nullable=True)             # which step failed, if any
    completed_steps = Column(Text, default="[]")            # JSON list of step names
    pipeline_error = Column(Text, nullable=True)            # JSON {type, message}
    created_at = Column(DateTime, server_default=func.now())
