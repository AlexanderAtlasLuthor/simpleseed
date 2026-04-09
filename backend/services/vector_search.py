"""
Semantic vector search over knowledge chunks.

Search strategy
---------------
1. Embed the query string via the embedding service.
2. Load all chunks that have embeddings from the DB.
3. Compute cosine similarity in-memory with numpy.
4. Return top-K results above SIMILARITY_THRESHOLD.

Scalability note
----------------
In-memory numpy similarity is adequate for up to ~50 000 chunks
(~400 MB of float32 data).  Beyond that, use pgvector:

  CREATE EXTENSION IF NOT EXISTS vector;
  ALTER TABLE knowledge_chunks ADD COLUMN embedding_vec vector(1536);
  UPDATE knowledge_chunks
    SET embedding_vec = embedding_json::jsonb::text::vector
    WHERE embedding_json IS NOT NULL;
  CREATE INDEX ON knowledge_chunks
    USING hnsw (embedding_vec vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

  Then replace the numpy block below with:
    from pgvector.sqlalchemy import Vector
    q = q.order_by(KnowledgeChunk.embedding_vec.cosine_distance(query_vec)).limit(top_k)

Owner scoping
-------------
The knowledge base is currently shared across all authenticated users
(no per-user ownership on KnowledgeDocument).  If user-scoped KB is
added later, add `.filter(KnowledgeDocument.user_id == user_id)` to
the query in _find_similar_chunks().

Fallback
--------
If OPENAI_API_KEY is absent, embed_query() returns None and
semantic_search() returns [] — the caller in knowledge.py then falls
back to keyword matching transparently.
"""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.30   # cosine similarity floor (0 = orthogonal, 1 = identical)
DEFAULT_TOP_K        = 5


# ── Public API ────────────────────────────────────────────────────────────────

def semantic_search(
    query: str,
    db: Session,
    top_k: int = DEFAULT_TOP_K,
    document_id: Optional[str] = None,
) -> list[dict]:
    """
    Find the top-K knowledge chunks most semantically similar to *query*.

    Returns a list of dicts compatible with the existing knowledge_context
    format consumed by generate_proposal():
        {
            "document_id":      str,
            "filename":         str,
            "chunk_id":         str,
            "chunk_index":      int,
            "snippet":          str,   # first 500 chars of chunk text
            "relevance_score":  float, # cosine similarity in [0, 1]
            "retrieval_method": "semantic",
        }

    Returns [] if embeddings are unavailable (triggers keyword fallback).
    """
    from services.embeddings import embed_query, embeddings_available

    if not embeddings_available():
        return []

    query_embedding = embed_query(query)
    if query_embedding is None:
        logger.warning("Query embedding failed — semantic search skipped")
        return []

    return _find_similar_chunks(query_embedding, db, top_k, document_id)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _find_similar_chunks(
    query_vec: list[float],
    db: Session,
    top_k: int,
    document_id: Optional[str],
) -> list[dict]:
    """
    Load embedded chunks, compute cosine similarity, return top-K results.
    """
    import numpy as np
    from models.knowledge_chunk import KnowledgeChunk
    from models.knowledge_document import KnowledgeDocument

    q = (
        db.query(KnowledgeChunk, KnowledgeDocument.filename)
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .filter(
            KnowledgeChunk.embedding_json.isnot(None),
            KnowledgeDocument.processing_status == "completed",
        )
    )
    if document_id:
        q = q.filter(KnowledgeChunk.document_id == document_id)

    rows = q.all()

    if not rows:
        logger.debug("No embedded chunks found — semantic search returns empty")
        return []

    # ── Build matrix ──────────────────────────────────────────────────────────
    query_arr  = np.array(query_vec, dtype=np.float32)
    query_norm = np.linalg.norm(query_arr)
    if query_norm == 0:
        return []
    query_unit = query_arr / query_norm

    chunk_objs: list[tuple] = []
    chunk_vecs: list[list]  = []

    for chunk, filename in rows:
        try:
            vec = json.loads(chunk.embedding_json)
            chunk_vecs.append(vec)
            chunk_objs.append((chunk, filename))
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("Skipping chunk %s — invalid embedding JSON", chunk.id)

    if not chunk_vecs:
        return []

    matrix = np.array(chunk_vecs, dtype=np.float32)       # (N, D)
    norms  = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms  = np.where(norms == 0, 1e-9, norms)             # avoid /0
    unit_matrix = matrix / norms

    similarities = unit_matrix @ query_unit                 # (N,) cosine sims

    # ── Rank and filter ───────────────────────────────────────────────────────
    indices = np.argsort(similarities)[::-1]

    results = []
    for idx in indices:
        if len(results) >= top_k:
            break
        sim = float(similarities[idx])
        if sim < SIMILARITY_THRESHOLD:
            break
        chunk, filename = chunk_objs[idx]
        results.append({
            "document_id":      chunk.document_id,
            "filename":         filename,
            "chunk_id":         chunk.id,
            "chunk_index":      chunk.chunk_index,
            "snippet":          chunk.text[:500],
            "relevance_score":  round(sim, 4),
            "retrieval_method": "semantic",
        })

    logger.debug(
        "semantic_search: %d results (pool=%d, threshold=%.2f, top_k=%d)",
        len(results), len(chunk_vecs), SIMILARITY_THRESHOLD, top_k,
    )
    return results
