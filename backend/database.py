from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

SQLALCHEMY_DATABASE_URL = "sqlite:///./simpleseed.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db():
    from models.rfp import RFP                              # noqa: F401
    from models.feedback import Feedback                    # noqa: F401
    from models.knowledge_document import KnowledgeDocument # noqa: F401
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate():
    """Add columns introduced after the initial schema without dropping data."""
    with engine.connect() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(rfps)"))}
        if "industry" not in existing:
            conn.execute(text("ALTER TABLE rfps ADD COLUMN industry TEXT DEFAULT 'general'"))
        if "risks" not in existing:
            conn.execute(text("ALTER TABLE rfps ADD COLUMN risks TEXT DEFAULT '[]'"))
        if "strategic_fit" not in existing:
            conn.execute(text("ALTER TABLE rfps ADD COLUMN strategic_fit TEXT DEFAULT '{}'"))
        if "knowledge_refs" not in existing:
            conn.execute(text("ALTER TABLE rfps ADD COLUMN knowledge_refs TEXT DEFAULT '[]'"))
        if "grounding_report" not in existing:
            conn.execute(text("ALTER TABLE rfps ADD COLUMN grounding_report TEXT DEFAULT '{}'"))
        conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
