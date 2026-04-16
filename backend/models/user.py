from sqlalchemy import Boolean, Column, String, DateTime
from sqlalchemy.sql import func
from database import Base


class User(Base):
    """
    Application user record.

    Each user belongs to an organisation (org_id).  All business objects
    (RFP, Feedback, KnowledgeDocument) carry the same org_id so every
    query can be scoped to a single organisation.

    org_id is auto-generated at registration time (uuid4).  Multiple users
    can share the same org_id if they register with the same UUID — a simple
    invite-by-token flow can use this later.
    """
    __tablename__ = "users"

    id              = Column(String,   primary_key=True)       # uuid4
    email           = Column(String,   nullable=False, unique=True, index=True)
    hashed_password = Column(String,   nullable=False)
    org_id          = Column(String,   nullable=False, index=True)  # uuid4, scopes all data
    is_active       = Column(Boolean,  default=True)
    created_at      = Column(DateTime, server_default=func.now())
