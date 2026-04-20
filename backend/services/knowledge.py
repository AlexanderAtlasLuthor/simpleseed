"""
Knowledge base service.

Storage layout
--------------
Text content  : backend/knowledge/{org_id}/{document_id}.txt
Metadata      : knowledge_documents table in SQLite/PostgreSQL

Each organisation's documents live in their own subdirectory, providing
hard filesystem isolation between tenants.  The search function only
scans the requesting org's directory — there is no cross-org fallback
and no production code path that writes or reads files outside
KNOWLEDGE_DIR/<org_id>/.

Supported input types
---------------------
application/pdf  → text extracted via parse_pdf() (reuses PDF pipeline)
text/plain       → read directly, UTF-8 with errors replaced

File size limit  → MAX_FILE_BYTES from config (same as RFP upload)
"""
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

import config as _config
from models.knowledge_document import KnowledgeDocument

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"

ALLOWED_EXTENSIONS = {".pdf", ".txt"}
ALLOWED_MIME_PREFIXES = {"application/pdf", "text/plain", "text/"}


# ── org_id validation ─────────────────────────────────────────────────────────

def _validate_org_id(org_id: str) -> None:
    """
    Validate that org_id is a well-formed UUID.  This is the only thing that
    stands between application code and arbitrary path composition — it must
    reject anything that could traverse outside KNOWLEDGE_DIR.
    """
    if not isinstance(org_id, str) or not org_id:
        raise ValueError("org_id must be a non-empty string.")
    try:
        uuid.UUID(org_id)
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"Invalid org_id format (expected UUID): {org_id!r}")


# ── Per-org directory helper ──────────────────────────────────────────────────

def _org_dir(org_id: str) -> Path:
    """
    Return (and create) the per-org subdirectory under KNOWLEDGE_DIR.

    Layout: backend/knowledge/<org_id>/

    Used ONLY by writers (upload_document).  Readers must never call this —
    they should use KNOWLEDGE_DIR / org_id directly so no directory is
    created as a side effect of a read.
    """
    _validate_org_id(org_id)
    d = KNOWLEDGE_DIR / org_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Search (read-only) ────────────────────────────────────────────────────────

def search_knowledge(
    query: str,
    top_k: int = 3,
    org_id: Optional[str] = None,
) -> list[dict]:
    """
    Return up to top_k documents most relevant to query by keyword overlap.

    Scope: only KNOWLEDGE_DIR/<org_id>/ is searched.  When org_id is None or
    falsey, an empty list is returned — there is deliberately no cross-org
    fallback.  This function is read-only: it never creates directories.
    """
    if not org_id:
        return []

    # Build the path directly — do NOT call _org_dir() here because that
    # would create an empty directory for every searching org as a side
    # effect of a read.
    search_dir = KNOWLEDGE_DIR / org_id
    if not search_dir.exists():
        return []

    query_words = set(query.lower().split())
    results: list[dict] = []

    for doc_path in search_dir.glob("*.txt"):
        try:
            content = doc_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        overlap = len(query_words & set(content.lower().split()))
        if overlap > 0:
            results.append({
                "document_id":     doc_path.stem,
                "filename":        doc_path.name,
                "snippet":         content[:500],
                "relevance_score": overlap,
            })

    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return results[:top_k]


# ── Upload pipeline ───────────────────────────────────────────────────────────

def upload_document(
    db: Session,
    filename: str,
    content_type: str,
    file_bytes: bytes,
    org_id: Optional[str] = None,
) -> KnowledgeDocument:
    """
    Validate, extract text, write to the org's directory, and create a
    DB metadata record.

    Text files are written to backend/knowledge/<org_id>/<doc_id>.txt.

    Raises:
      ValueError — if org_id is missing, if org_id is malformed, or if the
                   file fails validation (size, type, etc.)

    There is no fallback path that writes without an org_id.  Every
    knowledge document must belong to an organisation.
    """
    if not org_id:
        raise ValueError(
            "org_id is required for knowledge document upload. "
            "Every document must belong to an organisation."
        )
    _validate_org_id(org_id)
    _validate_upload(filename, content_type, len(file_bytes))

    doc_id = "doc_" + uuid.uuid4().hex

    # Create DB record in pending state first so it's visible even if extraction fails
    doc = KnowledgeDocument(
        id                = doc_id,
        filename          = filename,
        content_type      = _normalise_content_type(filename, content_type),
        source            = "internal_upload",
        processing_status = "pending",
        org_id            = org_id,
    )
    db.add(doc)
    db.commit()

    # Extract text and write to the org-scoped directory.  _org_dir creates
    # the directory if it does not yet exist — this is the only place that
    # is allowed to do so.
    try:
        text = _extract_text(doc_id, filename, content_type, file_bytes)
        text_path = _org_dir(org_id) / f"{doc_id}.txt"
        text_path.write_text(text, encoding="utf-8")

        doc.processing_status = "completed"
        doc.text_length       = len(text)
        doc.error_message     = None
    except Exception as exc:
        doc.processing_status = "error"
        doc.error_message     = str(exc)[:500]

    db.commit()
    db.refresh(doc)
    return doc


def list_documents(
    db: Session, org_id: Optional[str] = None
) -> list[dict]:
    """Return all knowledge documents ordered by upload date, newest first."""
    q = db.query(KnowledgeDocument)
    if org_id is not None:
        q = q.filter(KnowledgeDocument.org_id == org_id)
    rows = q.order_by(KnowledgeDocument.uploaded_at.desc()).all()
    return [_serialize(r) for r in rows]


def get_document(
    db: Session, doc_id: str, org_id: Optional[str] = None
) -> dict | None:
    q = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id)
    if org_id is not None:
        q = q.filter(KnowledgeDocument.org_id == org_id)
    row = q.first()
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
    import tempfile
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
