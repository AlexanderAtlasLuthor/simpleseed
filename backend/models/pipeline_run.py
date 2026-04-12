from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from database import Base


class PipelineRun(Base):
    """
    One row per pipeline execution (new analysis or retry).

    request_id is the primary correlation key that appears in:
      - structured step logs
      - LLMUsage rows
      - Sentry scope tags

    status reflects the final outcome of the entire pipeline, not individual steps.
    Individual step failures are tracked on the RFP row (failed_step, pipeline_error).
    """

    __tablename__ = "pipeline_runs"

    id                = Column(String,  primary_key=True)
    request_id        = Column(String,  nullable=True,  index=True)
    rfp_id            = Column(String,  nullable=True,  index=True)
    user_id           = Column(String,  nullable=True)
    status            = Column(String,  nullable=False)   # "success" | "failed"
    total_duration_ms = Column(Integer, nullable=True)
    created_at        = Column(DateTime, server_default=func.now())
