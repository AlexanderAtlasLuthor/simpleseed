"""
Knowledge base isolation tests.

Verifies that:
  - documents are written to org-specific subdirectories on disk
  - search_knowledge() only returns results from the queried org's directory
  - the analysis pipeline passes org_id to the search function
  - an org with no documents gets an empty result, not a crash
  - cross-org search is structurally impossible (not just policy)

Run with:
    cd backend && pytest tests/test_knowledge_isolation.py -v
"""
import json
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

# ── Bootstrap — must happen before any application imports ────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-for-knowledge-isolation-tests!")

from services.knowledge import (   # noqa: E402
    KNOWLEDGE_DIR,
    _org_dir,
    _validate_org_id,
    search_knowledge,
    upload_document,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_knowledge_root(tmp_path, monkeypatch):
    """
    Redirect KNOWLEDGE_DIR to a fresh temp directory for each test.
    Prevents tests from polluting the real backend/knowledge/ tree and from
    reading each other's files.
    """
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_path)
    return tmp_path


def _write_org_doc(knowledge_root: Path, org_id: str, doc_id: str, content: str) -> Path:
    """Directly write a .txt file into the org's subdirectory (bypasses DB)."""
    org_path = knowledge_root / org_id
    org_path.mkdir(parents=True, exist_ok=True)
    doc_path = org_path / f"{doc_id}.txt"
    doc_path.write_text(content, encoding="utf-8")
    return doc_path


# ── 1. Per-org directory helper ───────────────────────────────────────────────

def test_org_dir_creates_subdirectory(tmp_knowledge_root, monkeypatch):
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)
    org_id = str(uuid.uuid4())
    result = _org_dir(org_id)
    assert result == tmp_knowledge_root / org_id
    assert result.is_dir()


def test_org_dir_idempotent(tmp_knowledge_root, monkeypatch):
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)
    org_id = str(uuid.uuid4())
    _org_dir(org_id)
    _org_dir(org_id)  # second call must not raise
    assert (tmp_knowledge_root / org_id).is_dir()


# ── 2. Upload writes to correct org directory ─────────────────────────────────

def test_upload_writes_to_org_subdirectory(tmp_knowledge_root, monkeypatch):
    """
    upload_document() with an org_id must write the .txt file under
    backend/knowledge/<org_id>/<doc_id>.txt, not in the flat root.
    """
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    org_id = str(uuid.uuid4())
    file_content = b"Cloud infrastructure managed services proposal template"

    # Use a mock DB session — we're testing the file path, not the DB
    class _MockDB:
        def add(self, obj): pass
        def commit(self): pass
        def refresh(self, obj): pass

    doc = upload_document(
        db=_MockDB(),
        filename="test.txt",
        content_type="text/plain",
        file_bytes=file_content,
        org_id=org_id,
    )

    # File must be inside the org subdirectory
    expected_path = tmp_knowledge_root / org_id / f"{doc.id}.txt"
    assert expected_path.exists(), f"Expected file at {expected_path}"

    # No file must have landed in the flat root
    flat_files = list(tmp_knowledge_root.glob("*.txt"))
    assert flat_files == [], f"Files leaked to flat root: {flat_files}"


def test_upload_different_orgs_use_different_directories(tmp_knowledge_root, monkeypatch):
    """Two separate orgs' uploads must not share a directory."""
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())

    class _MockDB:
        def add(self, obj): pass
        def commit(self): pass
        def refresh(self, obj): pass

    doc_a = upload_document(
        db=_MockDB(), filename="a.txt", content_type="text/plain",
        file_bytes=b"federal contracting past performance", org_id=org_a,
    )
    doc_b = upload_document(
        db=_MockDB(), filename="b.txt", content_type="text/plain",
        file_bytes=b"commercial software development methodology", org_id=org_b,
    )

    assert (tmp_knowledge_root / org_a / f"{doc_a.id}.txt").exists()
    assert (tmp_knowledge_root / org_b / f"{doc_b.id}.txt").exists()

    # Org A's file must NOT appear in org B's directory
    assert not (tmp_knowledge_root / org_b / f"{doc_a.id}.txt").exists()
    assert not (tmp_knowledge_root / org_a / f"{doc_b.id}.txt").exists()


# ── 3. Search isolation ───────────────────────────────────────────────────────

def test_search_only_returns_own_org_documents(tmp_knowledge_root, monkeypatch):
    """
    Core isolation test: a search for org A must never surface org B's files,
    even when both orgs have documents containing the same keywords.
    """
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())
    shared_keyword = "quantum-cryptography-unique-term"

    _write_org_doc(tmp_knowledge_root, org_a, "doc_aaa", f"Org A proprietary: {shared_keyword} methodology")
    _write_org_doc(tmp_knowledge_root, org_b, "doc_bbb", f"Org B confidential: {shared_keyword} research")

    results_a = search_knowledge(shared_keyword, org_id=org_a)
    results_b = search_knowledge(shared_keyword, org_id=org_b)

    # Each org sees only their own document
    assert len(results_a) == 1
    assert results_a[0]["document_id"] == "doc_aaa"

    assert len(results_b) == 1
    assert results_b[0]["document_id"] == "doc_bbb"

    # Neither org sees the other's document
    a_ids = {r["document_id"] for r in results_a}
    b_ids = {r["document_id"] for r in results_b}
    assert "doc_bbb" not in a_ids, "Org A must not see org B document"
    assert "doc_aaa" not in b_ids, "Org B must not see org A document"


def test_search_without_org_id_returns_empty(tmp_knowledge_root, monkeypatch):
    """
    Calling search_knowledge with no org_id must return [] — no cross-org
    fallback, no global scan.
    """
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    # Write a file with no org affiliation (flat root, old-style)
    flat_doc = tmp_knowledge_root / "legacy_doc.txt"
    flat_doc.write_text("cloud security audit framework", encoding="utf-8")

    # Also write one in a real org dir
    org_id = str(uuid.uuid4())
    _write_org_doc(tmp_knowledge_root, org_id, "doc_real", "cloud security audit framework")

    # No org_id → must return empty
    results = search_knowledge("cloud security audit", org_id=None)
    assert results == [], f"Expected [] without org_id, got: {results}"


def test_search_empty_org_returns_empty_list(tmp_knowledge_root, monkeypatch):
    """An org with no uploaded documents must get [] without crashing."""
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    org_id = str(uuid.uuid4())
    # Do NOT create any files for this org — directory may not even exist

    results = search_knowledge("anything at all", org_id=org_id)
    assert results == []


def test_search_newly_created_org_dir_returns_empty(tmp_knowledge_root, monkeypatch):
    """An org directory that exists but is empty returns [] without crashing."""
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    org_id = str(uuid.uuid4())
    (tmp_knowledge_root / org_id).mkdir()  # empty dir, no .txt files

    results = search_knowledge("test query", org_id=org_id)
    assert results == []


def test_search_top_k_respected(tmp_knowledge_root, monkeypatch):
    """search_knowledge respects the top_k parameter."""
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    org_id = str(uuid.uuid4())
    keyword = "infrastructure"
    for i in range(5):
        _write_org_doc(
            tmp_knowledge_root, org_id,
            f"doc_{i:03d}",
            f"{keyword} " * (i + 1),  # ascending relevance
        )

    results = search_knowledge(keyword, top_k=2, org_id=org_id)
    assert len(results) == 2
    # Highest relevance first
    assert results[0]["relevance_score"] >= results[1]["relevance_score"]


# ── 4. Pipeline call-site: search passes rfp.org_id ──────────────────────────

def test_pipeline_calls_search_with_rfp_org_id():
    """
    Verify the analysis pipeline in main.py passes org_id= to search_knowledge().

    Uses AST inspection of the source file — no live import of main.py needed.
    This avoids dragging in the full FastAPI app (auth, crypto, DB) while still
    proving the call-site is correct.
    """
    import ast

    main_src = (Path(__file__).parent.parent / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(main_src)

    # Find the _execute_pipeline_steps function definition
    pipeline_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_execute_pipeline_steps":
            pipeline_fn = node
            break

    assert pipeline_fn is not None, "_execute_pipeline_steps not found in main.py"

    # Within that function, find every call to search_knowledge
    search_calls = []
    for node in ast.walk(pipeline_fn):
        if isinstance(node, ast.Call):
            func = node.func
            func_name = (
                func.id if isinstance(func, ast.Name) else
                func.attr if isinstance(func, ast.Attribute) else ""
            )
            if func_name == "search_knowledge":
                search_calls.append(node)

    assert search_calls, "No search_knowledge() call found in _execute_pipeline_steps"

    # Every call must pass org_id= as a keyword argument
    for call in search_calls:
        kwarg_names = {kw.arg for kw in call.keywords}
        assert "org_id" in kwarg_names, (
            f"search_knowledge() call at line {call.lineno} is missing the "
            "org_id= keyword argument — this is the cross-org leak"
        )


# ── 5. Legacy flat-root files are invisible to org searches ──────────────────

def test_legacy_flat_files_not_returned_in_org_search(tmp_knowledge_root, monkeypatch):
    """
    Files that were uploaded before the per-org migration (sitting in the flat
    root) must NOT appear in any org's search results after the fix.
    """
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    # Simulate a pre-migration file in the flat root
    (tmp_knowledge_root / "old_doc_abc123.txt").write_text(
        "legacy content pre migration important keyword", encoding="utf-8"
    )

    org_id = str(uuid.uuid4())
    results = search_knowledge("legacy content pre migration", org_id=org_id)

    assert results == [], (
        "Legacy flat-root files must not surface in per-org searches after migration"
    )


# ── 6. Regression tests for audit-reported runtime bugs ──────────────────────

class _MockDB:
    def add(self, obj): pass
    def commit(self): pass
    def refresh(self, obj): pass


def test_upload_without_org_id_raises(tmp_knowledge_root, monkeypatch):
    """
    upload_document() with a missing org_id MUST raise ValueError and MUST NOT
    write anything to disk.  Previously this silently fell through to the
    flat root, leaking documents outside any tenant's scope.
    """
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    with pytest.raises(ValueError, match="org_id is required"):
        upload_document(
            db=_MockDB(),
            filename="leak.txt",
            content_type="text/plain",
            file_bytes=b"sensitive data that must never land in the global root",
            org_id=None,
        )

    # No file must have been created anywhere under KNOWLEDGE_DIR
    leaked = list(tmp_knowledge_root.rglob("*.txt"))
    assert leaked == [], f"Files leaked despite missing org_id: {leaked}"


def test_upload_with_empty_org_id_raises(tmp_knowledge_root, monkeypatch):
    """Empty-string org_id is equally invalid and must not write anything."""
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    with pytest.raises(ValueError):
        upload_document(
            db=_MockDB(),
            filename="leak.txt",
            content_type="text/plain",
            file_bytes=b"x",
            org_id="",
        )

    assert list(tmp_knowledge_root.rglob("*.txt")) == []


def test_search_does_not_create_directory(tmp_knowledge_root, monkeypatch):
    """
    search_knowledge() is read-only.  Calling it for an org that has never
    uploaded anything must NOT leave a directory behind on disk.  The old
    code called _org_dir() in the read path, which did `mkdir(exist_ok=True)`.
    """
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    fresh_org = str(uuid.uuid4())
    assert not (tmp_knowledge_root / fresh_org).exists()

    results = search_knowledge("anything", org_id=fresh_org)

    assert results == []
    assert not (tmp_knowledge_root / fresh_org).exists(), (
        "search_knowledge must not create directories as a side effect of a read"
    )


def test_search_with_no_org_id_creates_no_directory(tmp_knowledge_root, monkeypatch):
    """Bare search with org_id=None must not touch the filesystem at all."""
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    before = set(tmp_knowledge_root.iterdir())
    search_knowledge("cloud", org_id=None)
    after = set(tmp_knowledge_root.iterdir())
    assert before == after


def test_invalid_org_id_rejected_by_validator():
    """
    _validate_org_id must reject anything that isn't a UUID.  This is the
    structural defense against path traversal via org_id.
    """
    bad_values = [
        "../etc/passwd",
        "..",
        "/",
        "some/subdir",
        "not-a-uuid",
        "",
        None,
        12345,
        ["uuid"],
    ]
    for bad in bad_values:
        with pytest.raises(ValueError):
            _validate_org_id(bad)


def test_org_dir_rejects_path_traversal(tmp_knowledge_root, monkeypatch):
    """_org_dir must refuse non-UUID inputs before touching the filesystem."""
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    with pytest.raises(ValueError):
        _org_dir("../escape")

    # Nothing must have been created
    assert list(tmp_knowledge_root.iterdir()) == []


def test_upload_rejects_malformed_org_id(tmp_knowledge_root, monkeypatch):
    """upload_document must reject non-UUID org_ids without writing anything."""
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    with pytest.raises(ValueError, match="Invalid org_id"):
        upload_document(
            db=_MockDB(),
            filename="x.txt",
            content_type="text/plain",
            file_bytes=b"content",
            org_id="../escape",
        )
    assert list(tmp_knowledge_root.rglob("*.txt")) == []


def test_pdf_upload_lands_in_org_dir(tmp_knowledge_root, monkeypatch):
    """
    PDF uploads must extract text and write to the org's subdirectory, same
    as .txt uploads.  We inject a stub services.parser so the real module
    (which pulls in pdfplumber / cryptography) never loads.
    """
    monkeypatch.setattr("services.knowledge.KNOWLEDGE_DIR", tmp_knowledge_root)

    # Stub services.parser in sys.modules — _extract_pdf does a lazy
    # `from services.parser import parse_pdf` so this intercept is sufficient.
    import sys, types
    fake_parser = types.ModuleType("services.parser")
    fake_parser.parse_pdf = lambda path: "extracted pdf body text for testing"
    monkeypatch.setitem(sys.modules, "services.parser", fake_parser)

    org_id = str(uuid.uuid4())
    doc = upload_document(
        db=_MockDB(),
        filename="past_performance.pdf",
        content_type="application/pdf",
        # Minimal bytes that satisfy size check (> 0)
        file_bytes=b"%PDF-1.4 fake pdf payload",
        org_id=org_id,
    )

    expected = tmp_knowledge_root / org_id / f"{doc.id}.txt"
    assert expected.exists(), f"PDF extraction output missing at {expected}"
    assert expected.read_text(encoding="utf-8") == "extracted pdf body text for testing"

    # Must not have leaked to flat root
    assert list(tmp_knowledge_root.glob("*.txt")) == []


def test_validate_org_id_accepts_valid_uuid():
    """Sanity: real UUIDs pass validation."""
    _validate_org_id(str(uuid.uuid4()))  # must not raise
    _validate_org_id(str(uuid.UUID("12345678-1234-5678-1234-567812345678")))
