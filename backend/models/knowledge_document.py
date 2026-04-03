from sqlalchemy import Column, String, Integer, Text, DateTime
from sqlalchemy.sql import func
from database import Base


class KnowledgeDocument(Base):
    """
    Metadata record for a document uploaded to the internal knowledge base.
    The extracted text is stored as {id}.txt in backend/knowledge/
    so the existing search_knowledge() function can read it without changes.
    """
    __tablename__ = "knowledge_documents"

    id                 = Column(String,  primary_key=True)    # "doc_" + uuid4 hex
    filename           = Column(String,  nullable=False)
    content_type       = Column(String,  nullable=False)       # "application/pdf" | "text/plain"
    source             = Column(String,  default="internal_upload")
    processing_status  = Column(String,  default="pending")   # "pending" | "completed" | "error"
    text_length        = Column(Integer, nullable=True)
    error_message      = Column(Text,    nullable=True)
    uploaded_at        = Column(DateTime, server_default=func.now())
