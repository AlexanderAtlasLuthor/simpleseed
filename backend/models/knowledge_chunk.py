"""
Knowledge chunk model.

Each KnowledgeChunk represents one semantically-bounded slice of a
KnowledgeDocument.  Embeddings are stored as JSON-encoded float arrays in
the embedding_json column — compatible with both SQLite (dev) and PostgreSQL
(prod).

pgvector migration path (future):
  When the corpus grows past ~50k chunks, add a dedicated VECTOR column and
  an HNSW index for sub-millisecond ANN search.  See docs/pgvector_migration.md
  (generated below) for the exact migration SQL.
"""
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from database import Base


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    # ── Identity ──────────────────────────────────────────────────────────────
    id = Column(String, primary_key=True)          # "chunk_" + uuid4 hex
    document_id = Column(
        String,
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index = Column(Integer, nullable=False)  # 0-based order within document

    # ── Content ───────────────────────────────────────────────────────────────
    text = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False)
    # SHA-256(text): idempotency check — unchanged text → skip re-embedding
    content_hash = Column(String(64), nullable=True, index=True)

    # ── Embedding ─────────────────────────────────────────────────────────────
    # JSON-encoded float array, e.g. "[0.123, -0.456, ...]"
    # NULL means this chunk has not been embedded yet (or embedding failed).
    embedding_json = Column(Text, nullable=True)
    embedding_model = Column(String(100), nullable=True)  # "text-embedding-3-small"
    embedding_dims = Column(Integer, nullable=True)        # 1536

    # ── Metadata (for observability and future citation features) ─────────────
    page_number = Column(Integer, nullable=True)
    section_heading = Column(String(500), nullable=True)
    # "text" | "header" — heuristic classification from chunker
    chunk_type = Column(String(50), nullable=False, default="text")

    created_at = Column(DateTime, server_default=func.now())
