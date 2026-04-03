"""
Verify knowledge upload, validation, and listing logic.
Uses an in-memory SQLite DB and a temp directory for text files.
No LLM calls, no external services.
"""
import sys, tempfile, os
from pathlib import Path
sys.path.insert(0, ".")

# ── Patch KNOWLEDGE_DIR to a temp dir so tests don't pollute backend/knowledge ──
import services.knowledge as kb_mod
_tmp_kb = tempfile.mkdtemp()
kb_mod.KNOWLEDGE_DIR = Path(_tmp_kb)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models.knowledge_document import KnowledgeDocument

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine)
db = Session()

from services.knowledge import (
    upload_document, list_documents, get_document,
    _validate_upload, ALLOWED_EXTENSIONS,
)
import config as cfg_mod

TINY_PDF_BYTES = b"%PDF-1.4 tiny invalid pdf"  # won't parse properly, but won't crash


# ── Case 1: valid TXT upload → completed ─────────────────────────────────────
txt_content = b"This is a past proposal for healthcare cloud migration.\n" * 50
doc = upload_document(db, "proposal_hc.txt", "text/plain", txt_content)
assert doc.processing_status == "completed", f"Expected completed: {doc.processing_status}"
assert doc.filename  == "proposal_hc.txt"
assert doc.document_id if hasattr(doc, "document_id") else doc.id
assert doc.id.startswith("doc_")
assert doc.content_type == "text/plain"
assert doc.text_length  == len(txt_content.decode("utf-8", errors="replace"))
assert doc.source       == "internal_upload"
# Text file should exist on disk
txt_file = Path(_tmp_kb) / f"{doc.id}.txt"
assert txt_file.exists(), "Text file not written to knowledge dir"
assert "healthcare" in txt_file.read_text()
print(f"Case 1 PASS: TXT upload → completed, text_length={doc.text_length}, file on disk")


# ── Case 2: valid PDF upload → completed or error (no real PDF parser in test) ─
# We use real parse_pdf which will fail on fake bytes, so status should be "error"
# but the DB record MUST still exist
doc2 = upload_document(db, "fake_doc.pdf", "application/pdf", TINY_PDF_BYTES)
assert doc2.id.startswith("doc_")
assert doc2.filename == "fake_doc.pdf"
assert doc2.processing_status in ("completed", "error"), \
    f"Must be completed or error: {doc2.processing_status}"
assert doc2.processing_status != "pending", "Should not stay in pending after upload"
print(f"Case 2 PASS: PDF upload → status='{doc2.processing_status}', record persisted either way")


# ── Case 3: unsupported extension → ValueError ───────────────────────────────
try:
    _validate_upload("doc.docx", "application/vnd.openxmlformats", 1000)
    assert False, "Should raise ValueError"
except ValueError as e:
    assert ".docx" in str(e) or "Unsupported" in str(e)
    assert ".pdf" in str(e) or ".txt" in str(e)  # lists allowed types
print(f"Case 3 PASS: .docx → ValueError with allowed types listed")


# ── Case 4: file too large → ValueError ──────────────────────────────────────
original_max = cfg_mod.MAX_FILE_BYTES
cfg_mod.MAX_FILE_BYTES = 100  # patch to 100 bytes
try:
    _validate_upload("big.txt", "text/plain", 200)
    assert False
except ValueError as e:
    assert "large" in str(e).lower() or "size" in str(e).lower()
finally:
    cfg_mod.MAX_FILE_BYTES = original_max
print(f"Case 4 PASS: oversized file → ValueError")


# ── Case 5: empty file → ValueError ──────────────────────────────────────────
try:
    _validate_upload("empty.txt", "text/plain", 0)
    assert False
except ValueError as e:
    assert "empty" in str(e).lower()
print(f"Case 5 PASS: empty file → ValueError")


# ── Case 6: list_documents returns both records ───────────────────────────────
docs = list_documents(db)
assert len(docs) == 2, f"Expected 2 docs, got {len(docs)}"
ids = {d["document_id"] for d in docs}
assert doc.id  in ids
assert doc2.id in ids
print(f"Case 6 PASS: list_documents returns {len(docs)} records")


# ── Case 7: get_document by id ────────────────────────────────────────────────
fetched = get_document(db, doc.id)
assert fetched is not None
assert fetched["filename"]         == "proposal_hc.txt"
assert fetched["processing_status"] == "completed"
assert fetched["text_length"]      == doc.text_length
assert fetched["uploaded_at"]      is not None
print(f"Case 7 PASS: get_document by id returns correct metadata")


# ── Case 8: get_document unknown id → None ───────────────────────────────────
missing = get_document(db, "doc_doesnotexist")
assert missing is None
print(f"Case 8 PASS: get_document for unknown id returns None")


# ── Case 9: serialized dict has all required fields ──────────────────────────
required = {"document_id","filename","content_type","source",
            "processing_status","text_length","error_message","uploaded_at"}
fetched2 = get_document(db, doc.id)
assert required.issubset(fetched2.keys()), \
    f"Missing fields: {required - fetched2.keys()}"
print(f"Case 9 PASS: serialized document has all {len(required)} required fields")


# ── Case 10: document_id is stable and unique ─────────────────────────────────
doc3 = upload_document(db, "another.txt", "text/plain", b"Another document content here.")
assert doc3.id != doc.id
assert doc3.id != doc2.id
assert doc3.id.startswith("doc_")
print(f"Case 10 PASS: each upload gets a unique doc_id")


# ── Case 11: ALLOWED_EXTENSIONS covers expected types ─────────────────────────
assert ".pdf" in ALLOWED_EXTENSIONS
assert ".txt" in ALLOWED_EXTENSIONS
print(f"Case 11 PASS: ALLOWED_EXTENSIONS = {sorted(ALLOWED_EXTENSIONS)}")


# ── Case 12: TXT content survives round-trip ─────────────────────────────────
unique_text = b"UNIQUE_TOKEN_FOR_ROUNDTRIP_TEST " * 10
doc4 = upload_document(db, "roundtrip.txt", "text/plain", unique_text)
stored_path = Path(_tmp_kb) / f"{doc4.id}.txt"
assert stored_path.exists()
stored_content = stored_path.read_text()
assert "UNIQUE_TOKEN_FOR_ROUNDTRIP_TEST" in stored_content
print(f"Case 12 PASS: TXT content survives round-trip to disk")


print("\nAll cases passed.")

# Cleanup temp dir
import shutil
shutil.rmtree(_tmp_kb, ignore_errors=True)
