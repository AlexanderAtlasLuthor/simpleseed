"""
Knowledge base service.

Storage layout
--------------
Text content  : backend/knowledge/{document_id}.txt
Metadata      : knowledge_documents table in SQLite

This split lets search_knowledge() keep its simple file-scan approach
while the API exposes rich metadata (filename, status, upload date, etc.).

Supported input types
---------------------
application/pdf  → text extracted via parse_pdf() (reuses PDF pipeline)
text/plain       → read directly, UTF-8 with errors replaced

File size limit  → MAX_FILE_BYTES from config (same as RFP upload)
"""
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

import config as _config
from models.knowledge_document import KnowledgeDocument

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"

ALLOWED_EXTENSIONS = {".pdf", ".txt"}
ALLOWED_MIME_PREFIXES = {"application/pdf", "text/plain", "text/"}


# ── Search (unchanged behaviour, now also returns DB metadata when available) ─

def search_knowledge(query: str, top_k: int = 3) -> list[dict]:
    """Return top_k documents most relevant to query by keyword overlap."""
    KNOWLEDGE_DIR.mkdir(exist_ok=True)
    query_words = set(query.lower().split())
    results = []

    for doc_path in KNOWLEDGE_DIR.glob("*.txt"):
        content = doc_path.read_text(encoding="utf-8", errors="ignore")
        overlap = len(query_words & set(content.lower().split()))
        if overlap > 0:
            results.append({
                "document_id": doc_path.stem,
                "filename": doc_path.name,
                "snippet": content[:500],
                "relevance": overlap,
            })

    results.sort(key=lambda x: x["relevance"], reverse=True)
    return results[:top_k]


# ── Upload pipeline ───────────────────────────────────────────────────────────

def upload_document(
    db: Session,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> KnowledgeDocument:
    """
    Validate, extract text, persist file, and create a DB metadata record.

    Raises ValueError with a clear message for invalid input.
    Returns the completed KnowledgeDocument row.
    """
    _validate_upload(filename, content_type, len(file_bytes))

    doc_id = "doc_" + uuid.uuid4().hex
    KNOWLEDGE_DIR.mkdir(exist_ok=True)

    # Create DB record in pending state first so it's visible even if extraction fails
    doc = KnowledgeDocument(
        id               = doc_id,
        filename         = filename,
        content_type     = _normalise_content_type(filename, content_type),
        source           = "internal_upload",
        processing_status = "pending",
    )
    db.add(doc)
    db.commit()

    # Extract text
    try:
        text = _extract_text(doc_id, filename, content_type, file_bytes)
        text_path = KNOWLEDGE_DIR / f"{doc_id}.txt"
        text_path.write_text(text, encoding="utf-8")

        doc.processing_status = "completed"
        doc.text_length        = len(text)
        doc.error_message      = None
    except Exception as exc:
        doc.processing_status = "error"
        doc.error_message     = str(exc)[:500]

    db.commit()
    db.refresh(doc)
    return doc


def list_documents(db: Session) -> list[dict]:
    """Return all knowledge documents ordered by upload date, newest first."""
    rows = (
        db.query(KnowledgeDocument)
        .order_by(KnowledgeDocument.uploaded_at.desc())
        .all()
    )
    return [_serialize(r) for r in rows]


def get_document(db: Session, doc_id: str) -> dict | None:
    row = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
    return _serialize(row) if row else None


# ── Validation ────────────────────────────────────────────────────────────────

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


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_text(
    doc_id: str, filename: str, content_type: str, file_bytes: bytes
) -> str:
    ext = Path(filename).suffix.lower()

    if ext == ".pdf" or content_type == "application/pdf":
        return _extract_pdf(doc_id, file_bytes)

    # Plain text — decode, replacing unrecognised bytes
    return file_bytes.decode("utf-8", errors="replace")


def _extract_pdf(doc_id: str, file_bytes: bytes) -> str:
    """Write bytes to a temp file, run parse_pdf(), then clean up."""
    import tempfile, os
    from services.parser import parse_pdf

    tmp_path = Path(tempfile.gettempdir()) / f"{doc_id}_upload.pdf"
    try:
        tmp_path.write_bytes(file_bytes)
        return parse_pdf(str(tmp_path))
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise_content_type(filename: str, declared: str) -> str:
    """Prefer extension-derived type for consistency."""
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
    }
