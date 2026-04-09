"""
Knowledge base service — upgraded in 1.2 with semantic retrieval.
"""
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

import config as _config
from models.knowledge_document import KnowledgeDocument

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
ALLOWED_EXTENSIONS    = {".pdf", ".txt"}
ALLOWED_MIME_PREFIXES = {"application/pdf", "text/plain", "text/"}


def search_knowledge(
    query: str,
    db: Optional[Session] = None,
    top_k: int = 5,
) -> list[dict]:
    """
    Return top-K knowledge items most relevant to *query*.
    Tries semantic search first; falls back to keyword if unavailable.
    """
    if db is not None:
        try:
            from services.vector_search import semantic_search
            results = semantic_search(query, db, top_k=top_k)
            if results:
                logger.debug("search_knowledge: semantic returned %d results", len(results))
                return results
            logger.debug("search_knowledge: semantic empty — falling back to keyword")
        except Exception as exc:
            logger.warning("Semantic search error (%s) — falling back to keyword", exc)
    return _keyword_search(query, top_k)


def upload_document(
    db: Session,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> KnowledgeDocument:
    """
    Validate, extract text, persist file, and create a DB metadata record.
    Chunking/embedding is done by a BackgroundTask in main.py via index_document_chunks().
    """
    _validate_upload(filename, content_type, len(file_bytes))

    doc_id = "doc_" + uuid.uuid4().hex
    KNOWLEDGE_DIR.mkdir(exist_ok=True)

    doc = KnowledgeDocument(
        id                = doc_id,
        filename          = filename,
        content_type      = _normalise_content_type(filename, content_type),
        source            = "internal_upload",
        processing_status = "pending",
        embedding_status  = "not_indexed",
        chunk_count       = 0,
    )
    db.add(doc)
    db.commit()

    try:
        text = _extract_text(doc_id, filename, content_type, file_bytes)
        (KNOWLEDGE_DIR / f"{doc_id}.txt").write_text(text, encoding="utf-8")
        doc.processing_status = "completed"
        doc.text_length       = len(text)
        doc.error_message     = None
    except Exception as exc:
        doc.processing_status = "error"
        doc.error_message     = str(exc)[:500]

    db.commit()
    db.refresh(doc)
    return doc


def index_document_chunks(doc_id: str, db: Session) -> None:
    """
    Chunk and embed a document, saving KnowledgeChunk rows to the DB.
    Idempotent: replaces existing chunks on re-run.
    """
    from models.knowledge_chunk import KnowledgeChunk
    from services.chunker import chunk_document
    from services.embeddings import embed_texts, EMBEDDING_MODEL

    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
    if not doc:
        logger.error("index_document_chunks: document %s not found", doc_id)
        return
    if doc.processing_status != "completed":
        logger.warning(
            "index_document_chunks: doc %s has status '%s' — skipping",
            doc_id, doc.processing_status,
        )
        return

    text_path = KNOWLEDGE_DIR / f"{doc_id}.txt"
    if not text_path.exists():
        logger.error("index_document_chunks: text file missing for doc %s", doc_id)
        doc.embedding_status = "failed"
        db.commit()
        return

    text = text_path.read_text(encoding="utf-8", errors="replace")
    doc.embedding_status = "pending"
    db.commit()

    chunks = chunk_document(text)
    logger.info("index_document_chunks: doc %s → %d chunks", doc_id, len(chunks))

    if not chunks:
        doc.embedding_status = "completed"
        doc.chunk_count      = 0
        db.commit()
        return

    # Delete existing chunks for idempotency
    deleted = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc_id).delete()
    if deleted:
        logger.debug("index_document_chunks: replaced %d old chunks for doc %s", deleted, doc_id)
    db.commit()

    chunk_texts = [c["text"] for c in chunks]
    embeddings  = embed_texts(chunk_texts)

    failed_count = 0
    for chunk_data, embedding in zip(chunks, embeddings):
        db.add(KnowledgeChunk(
            id              = "chunk_" + uuid.uuid4().hex,
            document_id     = doc_id,
            chunk_index     = chunk_data["chunk_index"],
            text            = chunk_data["text"],
            char_count      = chunk_data["char_count"],
            content_hash    = chunk_data["content_hash"],
            chunk_type      = chunk_data["chunk_type"],
            embedding_json  = json.dumps(embedding) if embedding is not None else None,
            embedding_model = EMBEDDING_MODEL if embedding is not None else None,
            embedding_dims  = len(embedding) if embedding is not None else None,
        ))
        if embedding is None:
            failed_count += 1
    db.commit()

    success_count = len(chunks) - failed_count
    if failed_count == 0:
        doc.embedding_status = "completed"
    elif success_count == 0:
        doc.embedding_status = "failed"
    else:
        doc.embedding_status = "partial"
    doc.chunk_count = len(chunks)
    db.commit()

    logger.info(
        "index_document_chunks: doc %s — %d/%d chunks embedded (status=%s)",
        doc_id, success_count, len(chunks), doc.embedding_status,
    )


def list_documents(db: Session) -> list[dict]:
    rows = db.query(KnowledgeDocument).order_by(KnowledgeDocument.uploaded_at.desc()).all()
    return [_serialize(r) for r in rows]


def get_document(db: Session, doc_id: str) -> dict | None:
    row = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
    return _serialize(row) if row else None


# ── Internal helpers ──────────────────────────────────────────────────────────

def _validate_upload(filename: str, content_type: str, size_bytes: int) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    if not any(content_type.startswith(p) for p in ALLOWED_MIME_PREFIXES):
        raise ValueError(
            f"Unsupported content type '{content_type}'. Upload a PDF or plain-text file."
        )
    if size_bytes > _config.MAX_FILE_BYTES:
        raise ValueError(
            f"File too large ({size_bytes // (1024*1024)} MB). "
            f"Maximum allowed size is {_config.MAX_FILE_BYTES // (1024*1024)} MB."
        )
    if size_bytes == 0:
        raise ValueError("File is empty.")


def _extract_text(
    doc_id: str, filename: str, content_type: str, file_bytes: bytes
) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf" or content_type == "application/pdf":
        return _extract_pdf(doc_id, file_bytes)
    return file_bytes.decode("utf-8", errors="replace")


def _extract_pdf(doc_id: str, file_bytes: bytes) -> str:
    import tempfile
    from services.parser import parse_pdf
    tmp_path = Path(tempfile.gettempdir()) / f"{doc_id}_upload.pdf"
    try:
        tmp_path.write_bytes(file_bytes)
        return parse_pdf(str(tmp_path))
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _keyword_search(query: str, top_k: int) -> list[dict]:
    """Original keyword-overlap search over .txt files — retained as fallback."""
    KNOWLEDGE_DIR.mkdir(exist_ok=True)
    query_words = set(query.lower().split())
    results = []
    for doc_path in KNOWLEDGE_DIR.glob("*.txt"):
        content = doc_path.read_text(encoding="utf-8", errors="ignore")
        overlap = len(query_words & set(content.lower().split()))
        if overlap > 0:
            results.append({
                "document_id":      doc_path.stem,
                "filename":         doc_path.name,
                "snippet":          content[:500],
                "relevance_score":  overlap,
                "retrieval_method": "keyword",
            })
    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return results[:top_k]


def _normalise_content_type(filename: str, declared: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return "application/pdf"
    if ext == ".txt":
        return "text/plain"
    return declared


def _serialize(doc: KnowledgeDocument) -> dict:
    return {
        "document_id":       doc.id,
        "filename":          doc.filename,
        "content_type":      doc.content_type,
        "source":            doc.source,
        "processing_status": doc.processing_status,
        "text_length":       doc.text_length,
        "error_message":     doc.error_message,
        "uploaded_at":       doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "embedding_status":  getattr(doc, "embedding_status", "not_indexed"),
        "chunk_count":       getattr(doc, "chunk_count", 0),
    }
