from sqlalchemy import Column, String, Integer, Float, DateTime
from sqlalchemy.sql import func
from database import Base


class LLMUsage(Base):
    """
    One row per Anthropic API call.

    request_id ties this record back to a PipelineRun and to the structured
    step logs for end-to-end tracing.

    service identifies which part of the pipeline made the call so per-step
    costs can be broken down without touching the service code.

    estimated_cost is derived at write time from a static pricing map — it is
    an approximation and should be treated as such.
    """

    __tablename__ = "llm_usage"

    id             = Column(String,  primary_key=True)
    request_id     = Column(String,  nullable=True,  index=True)
    user_id        = Column(String,  nullable=True,  index=True)
    model          = Column(String,  nullable=False)
    # extractor | generator | scoring | risks | profile | unknown
    service        = Column(String,  nullable=True)
    input_tokens   = Column(Integer, nullable=False, default=0)
    output_tokens  = Column(Integer, nullable=False, default=0)
    total_tokens   = Column(Integer, nullable=False, default=0)
    estimated_cost = Column(Float,   nullable=False, default=0.0)
    created_at     = Column(DateTime, server_default=func.now())
