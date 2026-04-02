from sqlalchemy import Column, String, Integer, Text, DateTime
from sqlalchemy.sql import func
from database import Base


class RFP(Base):
    __tablename__ = "rfps"

    id = Column(String, primary_key=True)
    filename = Column(String, nullable=False)
    original_text = Column(Text)
    requirements = Column(Text)
    proposal = Column(Text)
    score = Column(Integer, default=0)
    decision = Column(String, default="NO BID")
    score_breakdown = Column(Text, default="{}")
    reasoning = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now())
