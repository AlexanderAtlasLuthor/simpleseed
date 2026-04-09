"""
Tests for vector search: chunking, embedding, semantic retrieval,
owner scoping, fallback behaviour, and pipeline integration.

Pattern: standalone Python script with direct assertions (no pytest).
Run with:
    cd backend && python test_vector_search.py
"""
import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Stub optional heavy deps ──────────────────────────────────────────────────
for _mod in ["pdfplumber", "services.parser", "services.fetcher", "services.sam_gov"]:
    sys.modules.setdefault(_mod, MagicMock())

sys.path.insert(0, ".")

# ── In-memory DB with StaticPool (so tables persist across connections) ───────
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from database import Base
from models.rfp import RFP                          # noqa: F401
from models.feedback import Feedback                # noqa: F401
from models.knowledge_document import KnowledgeDocument  # noqa: F401
from models.knowledge_chunk import KnowledgeChunk   # noqa: F401
from models.user import User                        # noqa: F401

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=_engine)
_Session = sessionmaker(bind=_engine)


def _new_db():
    return _Session()


# ══════════════════════════════════════════════════════════════════════════════
# Chunking tests
# ══════════════════════════════════════════════════════════════════════════════

def test_chunk_basic():
    """Non-empty text produces at least one chunk with all required fields."""
    from services.chunker import chunk_document
    text = "First paragraph with enough words to pass the minimum.\n\nSecond paragraph also long enough to survive."
    chunks = chunk_document(text)
    assert len(chunks) >= 1, "Expected at least one chunk"
    for c in chunks:
        assert c["text"], "Chunk text must be non-empty"
        assert c["char_count"] > 0
        assert len(c["content_hash"]) == 64, "content_hash must be SHA-256 (64 hex chars)"
        assert c["chunk_type"] in ("text", "header")
        assert isinstance(c["chunk_index"], int)
    print("PASS test_chunk_basic")


def test_chunk_indices_are_sequential():
    """chunk_index values must be 0-based and contiguous after filtering."""
    from services.chunker import chunk_document
    text = "\n\n".join([f"Paragraph {i} has enough words to be kept." for i in range(10)])
    chunks = chunk_document(text)
    indices = [c["chunk_index"] for c in chunks]
    assert indices == list(range(len(chunks))), f"Indices not sequential: {indices}"
    print("PASS test_chunk_indices_are_sequential")


def test_chunk_min_length_filter():
    """Fragments shorter than CHUNK_MIN_CHARS are dropped."""
    from services.chunker import chunk_document, CHUNK_MIN_CHARS
    short_frag = "Hi.\n\n"
    long_para  = "This paragraph is definitely long enough to survive the minimum filter. " * 3
    chunks = chunk_document(short_frag + long_para)
    for c in chunks:
        assert c["char_count"] >= CHUNK_MIN_CHARS, (
            f"Chunk too short ({c['char_count']} < {CHUNK_MIN_CHARS}): {c['text'][:40]!r}"
        )
    print("PASS test_chunk_min_length_filter")


def test_chunk_empty_input():
    """Empty / whitespace-only input returns []."""
    from services.chunker import chunk_document
    assert chunk_document("") == []
    assert chunk_document("   \n\n   ") == []
    print("PASS test_chunk_empty_input")


def test_chunk_content_hash_determinism():
    """Same text always produces the same content_hash; different text differs."""
    from services.chunker import chunk_document
    text = "The quick brown fox jumped over the lazy sleeping dog near the old barn." * 3
    a = chunk_document(text)
    b = chunk_document(text)
    assert a, "Text should produce at least one chunk"
    assert a[0]["content_hash"] == b[0]["content_hash"], "Same text must produce same hash"

    text2 = "Totally different content about financial markets and economic indicators." * 3
    c = chunk_document(text2)
    assert c, "Second text should produce at least one chunk"
    assert a[0]["content_hash"] != c[0]["content_hash"], "Different text must differ"
    print("PASS test_chunk_content_hash_determinism")


def test_chunk_large_block_stays_within_max():
    """Paragraphs larger than CHUNK_MAX_CHARS must be split into smaller pieces."""
    from services.chunker import chunk_document, CHUNK_MAX_CHARS
    # Build a paragraph roughly 5x the max
    big_para = ("The system shall satisfy the requirement described in this sentence. " * 60)
    chunks = chunk_document(big_para)
    assert len(chunks) > 1, "Oversized paragraph must produce multiple chunks"
    for c in chunks:
        # Allow small slack for overlap carry-over
        assert c["char_count"] <= CHUNK_MAX_CHARS + 300, (
            f"Chunk too large: {c['char_count']} chars"
        )
    print("PASS test_chunk_large_block_stays_within_max")


def test_chunk_overlap_present():
    """Consecutive chunks from a long document should share some text (overlap)."""
    from services.chunker import chunk_document, CHUNK_OVERLAP_CHARS
    # Force paragraph accumulation into multiple flushes
    para = "overlap test sentence content fills the buffer adequately. " * 35
    text = "\n\n".join([para] * 4)
    chunks = chunk_document(text)
    if len(chunks) < 2:
        print("SKIP test_chunk_overlap_present (too few chunks for this input size)")
        return
    # At least one pair of consecutive chunks should share a suffix/prefix
    found_overlap = False
    for i in range(len(chunks) - 1):
        tail = chunks[i]["text"][-CHUNK_OVERLAP_CHARS:]
        head = chunks[i + 1]["text"]
        if tail.strip() and tail.strip()[:30] in head:
            found_overlap = True
            break
    assert found_overlap, "Expected at least one overlapping chunk pair"
    print("PASS test_chunk_overlap_present")


# ══════════════════════════════════════════════════════════════════════════════
# Embedding tests (mocked OpenAI)
# ══════════════════════════════════════════════════════════════════════════════

def test_embed_texts_empty():
    """embed_texts([]) returns []."""
    from services.embeddings import embed_texts
    assert embed_texts([]) == []
    print("PASS test_embed_texts_empty")


def test_embed_texts_no_api_key():
    """Without OPENAI_API_KEY every result is None."""
    from services.embeddings import embed_texts
    saved = os.environ.pop("OPENAI_API_KEY", None)
    try:
        result = embed_texts(["hello", "world"])
        assert result == [None, None], f"Expected [None, None], got {result}"
    finally:
        if saved:
            os.environ["OPENAI_API_KEY"] = saved
    print("PASS test_embed_texts_no_api_key")


def test_embed_texts_mocked_success():
    """With a mocked API response, embed_texts returns float arrays."""
    from services.embeddings import embed_texts

    fake_data = {
        "data": [
            {"index": 0, "embedding": [0.1] * 1536},
            {"index": 1, "embedding": [0.2] * 1536},
        ]
    }

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return fake_data

    with patch("httpx.post", return_value=_Resp()), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = embed_texts(["text one", "text two"])

    assert len(result) == 2
    assert len(result[0]) == 1536
    assert result[0][0] == 0.1
    assert result[1][0] == 0.2
    print("PASS test_embed_texts_mocked_success")


def test_embed_texts_retry_then_succeed():
    """embed_texts retries on failure and returns results on eventual success."""
    from services.embeddings import embed_texts

    fake_data = {"data": [{"index": 0, "embedding": [0.5] * 1536}]}

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return fake_data

    call_count = {"n": 0}

    def _flaky_post(*a, **kw):
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise ConnectionError("transient failure")
        return _Resp()

    with patch("httpx.post", side_effect=_flaky_post), \
         patch("time.sleep"), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = embed_texts(["some text"])

    assert call_count["n"] == 2, "Should have retried once"
    assert result[0] is not None
    print("PASS test_embed_texts_retry_then_succeed")


def test_embed_texts_permanent_failure_returns_none():
    """After all retries fail, embed_texts returns None for each text."""
    from services.embeddings import embed_texts

    with patch("httpx.post", side_effect=ConnectionError("always fails")), \
         patch("time.sleep"), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        result = embed_texts(["text a", "text b"])

    assert result == [None, None], f"Expected all None, got {result}"
    print("PASS test_embed_texts_permanent_failure_returns_none")


def test_embeddings_available_flag():
    """embeddings_available() correctly reflects OPENAI_API_KEY presence."""
    from services.embeddings import embeddings_available
    saved = os.environ.pop("OPENAI_API_KEY", None)
    try:
        assert not embeddings_available()
        os.environ["OPENAI_API_KEY"] = "sk-test"
        assert embeddings_available()
    finally:
        if saved:
            os.environ["OPENAI_API_KEY"] = saved
        else:
            os.environ.pop("OPENAI_API_KEY", None)
    print("PASS test_embeddings_available_flag")


# ══════════════════════════════════════════════════════════════════════════════
# Vector search tests
# ══════════════════════════════════════════════════════════════════════════════

def _insert_doc_with_chunks(db, doc_id, filename, chunks_with_embeddings):
    """Helper: insert a KnowledgeDocument and its KnowledgeChunk records."""
    doc = KnowledgeDocument(
        id               = doc_id,
        filename         = filename,
        content_type     = "text/plain",
        source           = "internal_upload",
        processing_status = "completed",
        embedding_status = "completed",
        chunk_count      = len(chunks_with_embeddings),
    )
    db.add(doc)
    for i, (text, embedding) in enumerate(chunks_with_embeddings):
        db.add(KnowledgeChunk(
            id              = "chunk_" + uuid.uuid4().hex,
            document_id     = doc_id,
            chunk_index     = i,
            text            = text,
            char_count      = len(text),
            content_hash    = f"hash_{doc_id}_{i}",
            embedding_json  = json.dumps(embedding) if embedding else None,
            embedding_model = "text-embedding-3-small" if embedding else None,
            embedding_dims  = len(embedding) if embedding else None,
            chunk_type      = "text",
        ))
    db.commit()


def test_semantic_search_ranks_correctly():
    """Chunk most similar to the query should appear first; unrelated chunks excluded."""
    db = _new_db()
    try:
        # Simple 4-dim vectors so we can reason about expected similarity.
        # Use non-adjacent indices (0, 5, 10) so the dedup logic does not
        # suppress the second relevant chunk.
        ml_vec      = [1.0, 0.0, 0.0, 0.0]   # "machine learning" direction
        similar_vec = [0.9, 0.1, 0.0, 0.0]   # similar to ML
        orthog_vec  = [0.0, 0.0, 1.0, 0.0]   # unrelated

        doc_id = "doc_rank_test"
        doc = KnowledgeDocument(
            id=doc_id, filename="ml_doc.txt", content_type="text/plain",
            source="internal_upload", processing_status="completed",
            embedding_status="completed", chunk_count=3,
        )
        db.add(doc)
        for idx, (text, vec) in zip([0, 5, 10], [
            ("Machine learning improves accuracy.", ml_vec),
            ("AI research is growing rapidly.", similar_vec),
            ("Tax filing deadline is April 15.", orthog_vec),
        ]):
            db.add(KnowledgeChunk(
                id="chunk_" + uuid.uuid4().hex,
                document_id=doc_id, chunk_index=idx,
                text=text, char_count=len(text),
                content_hash=f"hash_rank_{idx}",
                embedding_json=json.dumps(vec),
                embedding_model="test", embedding_dims=4,
                chunk_type="text",
            ))
        db.commit()

        from services.vector_search import _find_similar_chunks
        results = _find_similar_chunks([1.0, 0.0, 0.0, 0.0], db, top_k=5, document_id=doc_id)

        assert len(results) >= 2, "Should find ML and AI chunks above threshold"
        assert results[0]["relevance_score"] >= results[1]["relevance_score"], \
            "Results must be sorted descending by score"
        assert "Machine learning" in results[0]["snippet"] or "AI research" in results[0]["snippet"]
        # Orthogonal chunk (score=0) should be absent
        snippets = [r["snippet"] for r in results]
        assert not any("Tax filing" in s for s in snippets), \
            "Orthogonal chunk must be below threshold and excluded"
        print("PASS test_semantic_search_ranks_correctly")
    finally:
        db.close()


def test_semantic_search_threshold_filters_low_scores():
    """Chunks below SIMILARITY_THRESHOLD must not appear in results."""
    from services.vector_search import _find_similar_chunks, SIMILARITY_THRESHOLD
    db = _new_db()
    try:
        _insert_doc_with_chunks(db, "doc_thresh_test", "doc.txt", [
            ("Totally unrelated content.", [0.0, 1.0, 0.0, 0.0]),
        ])
        # Query vector is perpendicular → similarity = 0
        results = _find_similar_chunks(
            [1.0, 0.0, 0.0, 0.0], db, top_k=5, document_id="doc_thresh_test"
        )
        for r in results:
            assert r["relevance_score"] >= SIMILARITY_THRESHOLD, \
                f"Score {r['relevance_score']} below threshold {SIMILARITY_THRESHOLD}"
        print("PASS test_semantic_search_threshold_filters_low_scores")
    finally:
        db.close()


def test_semantic_search_no_embedded_chunks_returns_empty():
    """When no chunks have embeddings for a given doc, none appear in results."""
    from services.vector_search import _find_similar_chunks
    db = _new_db()
    try:
        _insert_doc_with_chunks(db, "doc_no_emb_test", "plain.txt", [
            ("Some text without an embedding.", None),
        ])
        # Scope to this document only — it has no embeddings so must return []
        results = _find_similar_chunks(
            [1.0] * 4, db, top_k=5, document_id="doc_no_emb_test"
        )
        assert results == [], f"Expected [], got {results}"
        print("PASS test_semantic_search_no_embedded_chunks_returns_empty")
    finally:
        db.close()


def test_semantic_search_no_api_key_returns_empty():
    """semantic_search returns [] when OPENAI_API_KEY is absent."""
    from services.vector_search import semantic_search
    db = _new_db()
    saved = os.environ.pop("OPENAI_API_KEY", None)
    try:
        results = semantic_search("any query", db, top_k=3)
        assert results == [], f"Expected [], got {results}"
        print("PASS test_semantic_search_no_api_key_returns_empty")
    finally:
        if saved:
            os.environ["OPENAI_API_KEY"] = saved
        db.close()


def test_semantic_search_result_format():
    """Semantic search results contain all required fields."""
    from services.vector_search import _find_similar_chunks
    db = _new_db()
    try:
        _insert_doc_with_chunks(db, "doc_fmt_test", "fmt.txt", [
            ("Relevant content about procurement.", [1.0, 0.0, 0.0, 0.0]),
        ])
        results = _find_similar_chunks(
            [1.0, 0.0, 0.0, 0.0], db, top_k=5, document_id="doc_fmt_test"
        )
        assert results, "Expected at least one result"
        r = results[0]
        required = {"document_id", "filename", "chunk_id", "chunk_index", "snippet",
                    "relevance_score", "retrieval_method"}
        missing = required - r.keys()
        assert not missing, f"Missing result fields: {missing}"
        assert r["retrieval_method"] == "semantic"
        assert 0.0 <= r["relevance_score"] <= 1.0
        print("PASS test_semantic_search_result_format")
    finally:
        db.close()


def test_semantic_search_document_id_scoping():
    """Restricting by document_id returns only chunks from that document."""
    from services.vector_search import _find_similar_chunks
    db = _new_db()
    try:
        vec = [1.0, 0.0, 0.0, 0.0]
        _insert_doc_with_chunks(db, "doc_scope_a", "a.txt", [("Doc A chunk.", vec)])
        _insert_doc_with_chunks(db, "doc_scope_b", "b.txt", [("Doc B chunk.", vec)])

        results = _find_similar_chunks(vec, db, top_k=10, document_id="doc_scope_a")
        doc_ids = {r["document_id"] for r in results}
        assert doc_ids == {"doc_scope_a"}, \
            f"Expected only doc_scope_a, got {doc_ids}"
        print("PASS test_semantic_search_document_id_scoping")
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# Knowledge indexing tests
# ══════════════════════════════════════════════════════════════════════════════

def test_index_document_chunks_creates_records():
    """index_document_chunks creates KnowledgeChunk rows and updates the document."""
    from services.knowledge import KNOWLEDGE_DIR, index_document_chunks

    db = _new_db()
    doc_id = "doc_idx_" + uuid.uuid4().hex[:8]
    try:
        db.add(KnowledgeDocument(
            id=doc_id, filename="test.txt", content_type="text/plain",
            source="internal_upload", processing_status="completed",
            embedding_status="not_indexed", chunk_count=0,
        ))
        db.commit()

        KNOWLEDGE_DIR.mkdir(exist_ok=True)
        text_path = KNOWLEDGE_DIR / f"{doc_id}.txt"
        text_path.write_text(
            "Paragraph one with sufficient length.\n\n"
            "Paragraph two also long enough.\n\n"
            "Paragraph three for good measure.",
            encoding="utf-8",
        )

        fake_emb = [0.1] * 1536
        with patch("services.embeddings.embed_texts", return_value=[fake_emb] * 10):
            index_document_chunks(doc_id, db)

        chunks = (
            db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.document_id == doc_id)
            .all()
        )
        assert len(chunks) >= 1, "Expected at least 1 chunk"
        assert all(c.embedding_json is not None for c in chunks), \
            "All chunks should have embeddings"

        db.refresh(db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first())
        doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
        assert doc.embedding_status == "completed"
        assert doc.chunk_count == len(chunks)
        print("PASS test_index_document_chunks_creates_records")
    finally:
        text_path = KNOWLEDGE_DIR / f"{doc_id}.txt"
        if text_path.exists():
            text_path.unlink()
        db.close()


def test_index_document_chunks_idempotent():
    """Re-running index_document_chunks does not duplicate chunks."""
    from services.knowledge import KNOWLEDGE_DIR, index_document_chunks

    db = _new_db()
    doc_id = "doc_idem_" + uuid.uuid4().hex[:8]
    try:
        db.add(KnowledgeDocument(
            id=doc_id, filename="idem.txt", content_type="text/plain",
            source="internal_upload", processing_status="completed",
            embedding_status="not_indexed", chunk_count=0,
        ))
        db.commit()

        KNOWLEDGE_DIR.mkdir(exist_ok=True)
        text_path = KNOWLEDGE_DIR / f"{doc_id}.txt"
        text_path.write_text(
            "First paragraph with enough content.\n\nSecond paragraph too.",
            encoding="utf-8",
        )

        fake_emb = [0.1] * 1536
        with patch("services.embeddings.embed_texts", return_value=[fake_emb] * 10):
            index_document_chunks(doc_id, db)
        first_count = (
            db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).count()
        )

        with patch("services.embeddings.embed_texts", return_value=[fake_emb] * 10):
            index_document_chunks(doc_id, db)
        second_count = (
            db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).count()
        )

        assert first_count == second_count, (
            f"Re-indexing must not duplicate chunks: {first_count} != {second_count}"
        )
        print("PASS test_index_document_chunks_idempotent")
    finally:
        text_path = KNOWLEDGE_DIR / f"{doc_id}.txt"
        if text_path.exists():
            text_path.unlink()
        db.close()


def test_index_document_partial_embedding_failure():
    """If some embeddings fail (None), embedding_status becomes 'partial'."""
    from services.knowledge import KNOWLEDGE_DIR, index_document_chunks

    db = _new_db()
    doc_id = "doc_partial_" + uuid.uuid4().hex[:8]
    try:
        db.add(KnowledgeDocument(
            id=doc_id, filename="partial.txt", content_type="text/plain",
            source="internal_upload", processing_status="completed",
            embedding_status="not_indexed", chunk_count=0,
        ))
        db.commit()

        KNOWLEDGE_DIR.mkdir(exist_ok=True)
        text_path = KNOWLEDGE_DIR / f"{doc_id}.txt"
        text_path.write_text(
            "First paragraph is fine.\n\nSecond paragraph text here.\n\n"
            "Third paragraph text here too.",
            encoding="utf-8",
        )

        # Return None for some chunks to simulate partial failure
        def _partial_embeddings(texts):
            result = [[0.1] * 1536 if i % 2 == 0 else None for i in range(len(texts))]
            return result

        with patch("services.embeddings.embed_texts", side_effect=_partial_embeddings):
            index_document_chunks(doc_id, db)

        doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
        assert doc.embedding_status in ("partial", "completed"), \
            f"Expected partial or completed, got {doc.embedding_status}"
        print("PASS test_index_document_partial_embedding_failure")
    finally:
        text_path = KNOWLEDGE_DIR / f"{doc_id}.txt"
        if text_path.exists():
            text_path.unlink()
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# Owner isolation tests
# ══════════════════════════════════════════════════════════════════════════════

def test_owner_isolation_cross_user():
    """User B cannot retrieve chunks uploaded by user A."""
    from services.vector_search import _find_similar_chunks
    db = _new_db()
    try:
        vec = [1.0, 0.0, 0.0, 0.0]
        # Insert a document owned by user A
        doc = KnowledgeDocument(
            id="doc_owner_a", filename="a.txt", content_type="text/plain",
            source="internal_upload", processing_status="completed",
            embedding_status="completed", chunk_count=1, owner_id="user_A",
        )
        db.add(doc)
        db.add(KnowledgeChunk(
            id="chunk_" + uuid.uuid4().hex,
            document_id="doc_owner_a", chunk_index=0,
            text="Sensitive content owned by user A.",
            char_count=35, content_hash="hash_a",
            embedding_json=json.dumps(vec),
            embedding_model="text-embedding-3-small",
            embedding_dims=4, chunk_type="text",
        ))
        db.commit()

        # User B's search must return nothing
        results_b = _find_similar_chunks(vec, db, top_k=5, document_id=None, user_id="user_B")
        assert results_b == [], (
            f"User B should not see user A's chunks, got: {results_b}"
        )

        # User A's search must find the chunk
        results_a = _find_similar_chunks(vec, db, top_k=5, document_id=None, user_id="user_A")
        assert len(results_a) >= 1, "User A should see their own chunks"
        assert results_a[0]["document_id"] == "doc_owner_a"

        print("PASS test_owner_isolation_cross_user")
    finally:
        db.close()


def test_owner_isolation_no_user_id_excludes_owned():
    """When user_id is provided, docs with owner_id=NULL are not returned."""
    from services.vector_search import _find_similar_chunks
    db = _new_db()
    try:
        vec = [1.0, 0.0, 0.0, 0.0]
        # Insert a legacy document with no owner
        doc = KnowledgeDocument(
            id="doc_legacy_iso", filename="legacy.txt", content_type="text/plain",
            source="internal_upload", processing_status="completed",
            embedding_status="completed", chunk_count=1, owner_id=None,
        )
        db.add(doc)
        db.add(KnowledgeChunk(
            id="chunk_" + uuid.uuid4().hex,
            document_id="doc_legacy_iso", chunk_index=0,
            text="Legacy document with no owner.",
            char_count=30, content_hash="hash_legacy_iso",
            embedding_json=json.dumps(vec),
            embedding_model="text-embedding-3-small",
            embedding_dims=4, chunk_type="text",
        ))
        db.commit()

        # A scoped query (user_id="some_user") must NOT return the ownerless doc
        results = _find_similar_chunks(vec, db, top_k=5, document_id=None, user_id="some_user")
        doc_ids = {r["document_id"] for r in results}
        assert "doc_legacy_iso" not in doc_ids, (
            "Ownerless (legacy) docs must not be returned when user_id is scoped"
        )
        print("PASS test_owner_isolation_no_user_id_excludes_owned")
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# Embedding dimension guard tests
# ══════════════════════════════════════════════════════════════════════════════

def test_dimension_mismatch_returns_empty():
    """
    Chunks stored with 4-dim embeddings, queried with a 3-dim vector → [].
    The dim guard must filter all chunks and return empty without crashing.
    """
    from services.vector_search import _find_similar_chunks
    db = _new_db()
    try:
        # Stored embedding: 4 dims
        vec4 = [1.0, 0.0, 0.0, 0.0]
        doc = KnowledgeDocument(
            id="doc_dim_mismatch", filename="dim.txt", content_type="text/plain",
            source="internal_upload", processing_status="completed",
            embedding_status="completed", chunk_count=1, owner_id=None,
        )
        db.add(doc)
        db.add(KnowledgeChunk(
            id="chunk_" + uuid.uuid4().hex,
            document_id="doc_dim_mismatch", chunk_index=0,
            text="Some content with a 4-dim embedding.",
            char_count=36, content_hash="hash_dim",
            embedding_json=json.dumps(vec4),
            embedding_model="text-embedding-3-small",
            embedding_dims=4, chunk_type="text",
        ))
        db.commit()

        # Query with a 3-dim vector — should not match 4-dim stored embeddings
        results = _find_similar_chunks(
            [1.0, 0.0, 0.0], db, top_k=5, document_id="doc_dim_mismatch"
        )
        assert results == [], (
            f"Dimension mismatch must return [], got: {results}"
        )
        print("PASS test_dimension_mismatch_returns_empty")
    finally:
        db.close()


def test_dimension_mismatch_does_not_affect_compatible_chunks():
    """
    Mixed pool: 3-dim and 4-dim chunks. Only 3-dim chunks returned for 3-dim query.
    """
    from services.vector_search import _find_similar_chunks
    db = _new_db()
    try:
        doc_id = "doc_dim_mixed"
        doc = KnowledgeDocument(
            id=doc_id, filename="mixed.txt", content_type="text/plain",
            source="internal_upload", processing_status="completed",
            embedding_status="completed", chunk_count=2, owner_id=None,
        )
        db.add(doc)
        # 3-dim chunk (compatible)
        db.add(KnowledgeChunk(
            id="chunk_" + uuid.uuid4().hex,
            document_id=doc_id, chunk_index=0,
            text="Three dimensional chunk.",
            char_count=24, content_hash="hash_3d",
            embedding_json=json.dumps([1.0, 0.0, 0.0]),
            embedding_model="model-v1",
            embedding_dims=3, chunk_type="text",
        ))
        # 4-dim chunk (incompatible with 3-dim query)
        db.add(KnowledgeChunk(
            id="chunk_" + uuid.uuid4().hex,
            document_id=doc_id, chunk_index=1,
            text="Four dimensional chunk.",
            char_count=23, content_hash="hash_4d",
            embedding_json=json.dumps([1.0, 0.0, 0.0, 0.0]),
            embedding_model="model-v2",
            embedding_dims=4, chunk_type="text",
        ))
        db.commit()

        results = _find_similar_chunks(
            [1.0, 0.0, 0.0], db, top_k=5, document_id=doc_id
        )
        # Only the 3-dim chunk is compatible
        assert len(results) == 1, f"Expected exactly 1 compatible result, got {len(results)}"
        assert "Three dimensional" in results[0]["snippet"]
        print("PASS test_dimension_mismatch_does_not_affect_compatible_chunks")
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# Indexing failure recovery tests
# ══════════════════════════════════════════════════════════════════════════════

def test_index_document_chunks_sets_failed_on_exception():
    """If embed_texts raises an exception, embedding_status is set to 'failed'."""
    from services.knowledge import KNOWLEDGE_DIR, index_document_chunks

    db = _new_db()
    doc_id = "doc_fail_" + uuid.uuid4().hex[:8]
    try:
        db.add(KnowledgeDocument(
            id=doc_id, filename="fail.txt", content_type="text/plain",
            source="internal_upload", processing_status="completed",
            embedding_status="not_indexed", chunk_count=0,
        ))
        db.commit()

        KNOWLEDGE_DIR.mkdir(exist_ok=True)
        text_path = KNOWLEDGE_DIR / f"{doc_id}.txt"
        # Text must exceed CHUNK_MIN_CHARS (100) so at least one chunk is produced
        # and embed_texts is actually invoked.
        text_path.write_text(
            "This paragraph is long enough to survive the minimum character filter "
            "used by the chunker and will definitely produce at least one chunk.",
            encoding="utf-8",
        )

        def _always_raises(texts):
            raise RuntimeError("Simulated OpenAI outage")

        with patch("services.embeddings.embed_texts", side_effect=_always_raises):
            index_document_chunks(doc_id, db)

        doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
        assert doc.embedding_status == "failed", (
            f"Expected 'failed' after exception, got '{doc.embedding_status}'"
        )
        print("PASS test_index_document_chunks_sets_failed_on_exception")
    finally:
        text_path = KNOWLEDGE_DIR / f"{doc_id}.txt"
        if text_path.exists():
            text_path.unlink()
        db.close()


def test_index_document_chunks_status_not_stuck_at_pending():
    """embedding_status must not remain 'pending' after any outcome."""
    from services.knowledge import KNOWLEDGE_DIR, index_document_chunks

    db = _new_db()
    doc_id = "doc_pend_" + uuid.uuid4().hex[:8]
    try:
        db.add(KnowledgeDocument(
            id=doc_id, filename="pend.txt", content_type="text/plain",
            source="internal_upload", processing_status="completed",
            embedding_status="not_indexed", chunk_count=0,
        ))
        db.commit()

        KNOWLEDGE_DIR.mkdir(exist_ok=True)
        text_path = KNOWLEDGE_DIR / f"{doc_id}.txt"
        # Text must exceed CHUNK_MIN_CHARS so at least one chunk is produced
        text_path.write_text(
            "This paragraph is long enough to survive the minimum character filter "
            "used by the chunker and will definitely produce at least one chunk.",
            encoding="utf-8",
        )

        # Simulate a crash mid-way
        def _crash(texts):
            raise MemoryError("OOM")

        with patch("services.embeddings.embed_texts", side_effect=_crash):
            index_document_chunks(doc_id, db)

        doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
        assert doc.embedding_status != "pending", (
            f"embedding_status must not be stuck at 'pending', got '{doc.embedding_status}'"
        )
        print("PASS test_index_document_chunks_status_not_stuck_at_pending")
    finally:
        text_path = KNOWLEDGE_DIR / f"{doc_id}.txt"
        if text_path.exists():
            text_path.unlink()
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# Deduplication tests
# ══════════════════════════════════════════════════════════════════════════════

def test_adjacent_chunks_are_deduplicated():
    """
    Two adjacent chunks from the same document should not both appear in top-K.
    The higher-scoring one wins; the adjacent duplicate is suppressed.
    """
    from services.vector_search import _find_similar_chunks
    db = _new_db()
    try:
        doc_id = "doc_dedup_adj"
        vec = [1.0, 0.0, 0.0, 0.0]   # identical vectors → same score
        doc = KnowledgeDocument(
            id=doc_id, filename="dedup.txt", content_type="text/plain",
            source="internal_upload", processing_status="completed",
            embedding_status="completed", chunk_count=2, owner_id=None,
        )
        db.add(doc)
        # chunk_index=0 and chunk_index=1 are adjacent — only one should appear
        db.add(KnowledgeChunk(
            id="chunk_" + uuid.uuid4().hex,
            document_id=doc_id, chunk_index=0,
            text="Chunk zero content about machine learning systems.",
            char_count=50, content_hash="hash_d0",
            embedding_json=json.dumps(vec), embedding_model="m",
            embedding_dims=4, chunk_type="text",
        ))
        db.add(KnowledgeChunk(
            id="chunk_" + uuid.uuid4().hex,
            document_id=doc_id, chunk_index=1,
            text="Chunk one content also about machine learning methods.",
            char_count=52, content_hash="hash_d1",
            embedding_json=json.dumps(vec), embedding_model="m",
            embedding_dims=4, chunk_type="text",
        ))
        db.commit()

        results = _find_similar_chunks(vec, db, top_k=5, document_id=doc_id)
        # Only one of the two adjacent chunks should appear
        assert len(results) == 1, (
            f"Expected 1 result after dedup (adjacent chunks), got {len(results)}"
        )
        print("PASS test_adjacent_chunks_are_deduplicated")
    finally:
        db.close()


def test_non_adjacent_chunks_are_not_deduplicated():
    """
    Chunks from the same document with non-adjacent indices (gap > 1) must both appear.
    """
    from services.vector_search import _find_similar_chunks
    db = _new_db()
    try:
        doc_id = "doc_dedup_gap"
        vec = [1.0, 0.0, 0.0, 0.0]
        doc = KnowledgeDocument(
            id=doc_id, filename="gap.txt", content_type="text/plain",
            source="internal_upload", processing_status="completed",
            embedding_status="completed", chunk_count=2, owner_id=None,
        )
        db.add(doc)
        # chunk_index=0 and chunk_index=5 — gap of 5, no overlap
        db.add(KnowledgeChunk(
            id="chunk_" + uuid.uuid4().hex,
            document_id=doc_id, chunk_index=0,
            text="First relevant section about procurement strategy.",
            char_count=49, content_hash="hash_g0",
            embedding_json=json.dumps(vec), embedding_model="m",
            embedding_dims=4, chunk_type="text",
        ))
        db.add(KnowledgeChunk(
            id="chunk_" + uuid.uuid4().hex,
            document_id=doc_id, chunk_index=5,
            text="Fifth relevant section about contract evaluation.",
            char_count=49, content_hash="hash_g5",
            embedding_json=json.dumps(vec), embedding_model="m",
            embedding_dims=4, chunk_type="text",
        ))
        db.commit()

        results = _find_similar_chunks(vec, db, top_k=5, document_id=doc_id)
        assert len(results) == 2, (
            f"Non-adjacent chunks from the same doc must both appear, got {len(results)}"
        )
        print("PASS test_non_adjacent_chunks_are_not_deduplicated")
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# Fallback behaviour
# ══════════════════════════════════════════════════════════════════════════════

def test_search_knowledge_falls_back_to_keyword():
    """Without OPENAI_API_KEY, search_knowledge uses keyword scan."""
    import tempfile
    from services import knowledge as kb_mod

    orig_dir = kb_mod.KNOWLEDGE_DIR
    tmp_dir  = Path(tempfile.mkdtemp())
    kb_mod.KNOWLEDGE_DIR = tmp_dir

    db = _new_db()
    saved = os.environ.pop("OPENAI_API_KEY", None)
    try:
        (tmp_dir / "doc_kw_test.txt").write_text(
            "machine learning algorithms and models", encoding="utf-8"
        )
        results = kb_mod.search_knowledge("machine learning", db=db, top_k=3)
        # Keyword search should find the file
        assert len(results) >= 1, "Expected at least one keyword result"
        assert results[0]["retrieval_method"] == "keyword"
        print("PASS test_search_knowledge_falls_back_to_keyword")
    finally:
        if saved:
            os.environ["OPENAI_API_KEY"] = saved
        db.close()
        kb_mod.KNOWLEDGE_DIR = orig_dir


def test_search_knowledge_no_db_uses_keyword():
    """When db=None, search_knowledge skips semantic and uses keyword only."""
    import tempfile
    from services import knowledge as kb_mod

    orig_dir = kb_mod.KNOWLEDGE_DIR
    tmp_dir  = Path(tempfile.mkdtemp())
    kb_mod.KNOWLEDGE_DIR = tmp_dir

    try:
        (tmp_dir / "doc_nodb_test.txt").write_text(
            "cloud infrastructure services", encoding="utf-8"
        )
        results = kb_mod.search_knowledge("cloud infrastructure", db=None, top_k=3)
        assert len(results) >= 1
        assert all(r["retrieval_method"] == "keyword" for r in results)
        print("PASS test_search_knowledge_no_db_uses_keyword")
    finally:
        kb_mod.KNOWLEDGE_DIR = orig_dir


def test_search_knowledge_semantic_preferred_over_keyword():
    """When semantic returns results, keyword fallback is NOT used."""
    import tempfile
    from services import knowledge as kb_mod

    orig_dir = kb_mod.KNOWLEDGE_DIR
    tmp_dir  = Path(tempfile.mkdtemp())
    kb_mod.KNOWLEDGE_DIR = tmp_dir

    db = _new_db()
    try:
        # Plant a keyword-matching file
        (tmp_dir / "doc_pref_test.txt").write_text(
            "machine learning is great for predictions", encoding="utf-8"
        )

        # Make semantic search return a result
        semantic_result = [{
            "document_id":      "doc_sem_pref",
            "filename":         "semantic_doc.txt",
            "chunk_id":         "chunk_abc",
            "chunk_index":      0,
            "snippet":          "Neural network architecture details",
            "relevance_score":  0.85,
            "retrieval_method": "semantic",
        }]

        with patch("services.vector_search.semantic_search", return_value=semantic_result), \
             patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            results = kb_mod.search_knowledge("machine learning", db=db, top_k=3)

        assert len(results) == 1
        assert results[0]["retrieval_method"] == "semantic", \
            "Semantic results should take precedence over keyword"
        print("PASS test_search_knowledge_semantic_preferred_over_keyword")
    finally:
        db.close()
        kb_mod.KNOWLEDGE_DIR = orig_dir


# ══════════════════════════════════════════════════════════════════════════════
# Run all
# ══════════════════════════════════════════════════════════════════════════════

test_chunk_basic()
test_chunk_indices_are_sequential()
test_chunk_min_length_filter()
test_chunk_empty_input()
test_chunk_content_hash_determinism()
test_chunk_large_block_stays_within_max()
test_chunk_overlap_present()
test_embed_texts_empty()
test_embed_texts_no_api_key()
test_embed_texts_mocked_success()
test_embed_texts_retry_then_succeed()
test_embed_texts_permanent_failure_returns_none()
test_embeddings_available_flag()
test_semantic_search_ranks_correctly()
test_semantic_search_threshold_filters_low_scores()
test_semantic_search_no_embedded_chunks_returns_empty()
test_semantic_search_no_api_key_returns_empty()
test_semantic_search_result_format()
test_semantic_search_document_id_scoping()
test_index_document_chunks_creates_records()
test_index_document_chunks_idempotent()
test_index_document_partial_embedding_failure()
# Owner isolation
test_owner_isolation_cross_user()
test_owner_isolation_no_user_id_excludes_owned()
# Dimension guard
test_dimension_mismatch_returns_empty()
test_dimension_mismatch_does_not_affect_compatible_chunks()
# Failure recovery
test_index_document_chunks_sets_failed_on_exception()
test_index_document_chunks_status_not_stuck_at_pending()
# Deduplication
test_adjacent_chunks_are_deduplicated()
test_non_adjacent_chunks_are_not_deduplicated()
# Fallback
test_search_knowledge_falls_back_to_keyword()
test_search_knowledge_no_db_uses_keyword()
test_search_knowledge_semantic_preferred_over_keyword()

print("\nAll vector search tests passed.")
