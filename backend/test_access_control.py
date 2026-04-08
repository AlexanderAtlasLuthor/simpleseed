"""
Tests for data isolation and ownership enforcement.

Proves that user A cannot read, update, or delete user B's RFPs, and
that each user only sees their own RFPs in list views.

Strategy:
- In-memory SQLite DB (same pattern as other test files)
- Two real user accounts (Alice and Bob)
- Real RFP records inserted directly via DB session
- HTTP requests via FastAPI TestClient with Bearer tokens
- Pipeline service calls are mocked so no LLM is invoked

Run with:
    cd backend && python test_access_control.py
"""
import sys, json
from unittest.mock import MagicMock, patch

for _mod in ["pdfplumber", "services.parser", "services.fetcher", "services.sam_gov"]:
    sys.modules.setdefault(_mod, MagicMock())

sys.path.insert(0, ".")

# ── In-memory DB ──────────────────────────────────────────────────────────────
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models.rfp import RFP
from models.feedback import Feedback    # noqa: F401
from models.knowledge_document import KnowledgeDocument  # noqa: F401
from models.user import User            # noqa: F401

_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=_engine)
_Session = sessionmaker(bind=_engine)

def _new_db():
    return _Session()

# ── TestClient ────────────────────────────────────────────────────────────────
from fastapi.testclient import TestClient
import main as main_mod

def _override_get_db():
    db = _Session()
    try:
        yield db
    finally:
        db.close()

main_mod.app.dependency_overrides[main_mod.get_db] = _override_get_db
client = TestClient(main_mod.app, raise_server_exceptions=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def register_and_login(email: str, password: str = "testpassword1") -> str:
    """Register a user and return their access token."""
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, f"Register failed: {r.text}"
    return r.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def insert_rfp(user_id: str, filename: str = "test.pdf") -> str:
    """Insert a minimal RFP record directly into the DB and return its ID."""
    import uuid
    rfp_id = str(uuid.uuid4())
    db = _new_db()
    try:
        rfp = RFP(
            id=rfp_id,
            user_id=user_id,
            filename=filename,
            original_text="RFP content",
            requirements=json.dumps({"summary": "test summary"}),
            proposal="Draft proposal",
            score=75,
            decision="BID",
            score_breakdown="{}",
            reasoning="Good fit",
            industry="general",
            risks="[]",
            strategic_fit="{}",
            knowledge_refs="[]",
            grounding_report="{}",
            pipeline_status="completed",
            completed_steps=json.dumps(["requirement_extraction", "proposal_generation", "bid_scoring"]),
        )
        db.add(rfp)
        db.commit()
    finally:
        db.close()
    return rfp_id


# ═══════════════════════════════════════════════════════════════════════════
# Setup: create Alice and Bob
# ═══════════════════════════════════════════════════════════════════════════
alice_token = register_and_login("alice@acme.com", "alicepass1")
bob_token   = register_and_login("bob@corp.com",   "bobpassword1")

# Fetch their user IDs from /api/auth/me
alice_id = client.get("/api/auth/me", headers=auth_headers(alice_token)).json()["id"]
bob_id   = client.get("/api/auth/me", headers=auth_headers(bob_token)).json()["id"]


# ═══════════════════════════════════════════════════════════════════════════
# Case 1: list_rfps returns only the current user's records
# ═══════════════════════════════════════════════════════════════════════════
def test_list_isolation():
    alice_rfp = insert_rfp(alice_id, "alice_rfp.pdf")
    bob_rfp   = insert_rfp(bob_id,   "bob_rfp.pdf")

    alice_list = client.get("/api/rfps", headers=auth_headers(alice_token)).json()
    bob_list   = client.get("/api/rfps", headers=auth_headers(bob_token)).json()

    alice_ids = {r["id"] for r in alice_list}
    bob_ids   = {r["id"] for r in bob_list}

    assert alice_rfp in alice_ids, "Alice must see her own RFP"
    assert bob_rfp   not in alice_ids, "Alice must NOT see Bob's RFP"
    assert bob_rfp   in bob_ids,   "Bob must see his own RFP"
    assert alice_rfp not in bob_ids,   "Bob must NOT see Alice's RFP"
    print("PASS test_list_isolation")


# ═══════════════════════════════════════════════════════════════════════════
# Case 2: user A cannot read user B's RFP by ID
# ═══════════════════════════════════════════════════════════════════════════
def test_read_cross_user():
    bob_rfp = insert_rfp(bob_id, "bob_secret.pdf")

    # Alice tries to read Bob's RFP — must get 404 (not 403, to avoid leaking existence).
    r = client.get(f"/api/rfps/{bob_rfp}", headers=auth_headers(alice_token))
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    # Bob can read his own RFP.
    r2 = client.get(f"/api/rfps/{bob_rfp}", headers=auth_headers(bob_token))
    assert r2.status_code == 200, f"Bob should access his own RFP: {r2.text}"
    print("PASS test_read_cross_user")


# ═══════════════════════════════════════════════════════════════════════════
# Case 3: user A cannot delete user B's RFP
# ═══════════════════════════════════════════════════════════════════════════
def test_delete_cross_user():
    bob_rfp = insert_rfp(bob_id, "bob_to_delete.pdf")

    # Alice tries to delete Bob's RFP.
    r = client.delete(f"/api/rfps/{bob_rfp}", headers=auth_headers(alice_token))
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    # Bob's RFP must still exist.
    r2 = client.get(f"/api/rfps/{bob_rfp}", headers=auth_headers(bob_token))
    assert r2.status_code == 200, "Bob's RFP must survive Alice's delete attempt"
    print("PASS test_delete_cross_user")


# ═══════════════════════════════════════════════════════════════════════════
# Case 4: user A cannot retry user B's RFP
# ═══════════════════════════════════════════════════════════════════════════
def test_retry_cross_user():
    # Insert a partial_failure RFP belonging to Bob.
    import uuid
    rfp_id = str(uuid.uuid4())
    db = _new_db()
    try:
        rfp = RFP(
            id=rfp_id,
            user_id=bob_id,
            filename="bob_partial.pdf",
            original_text="Some RFP text",
            requirements="{}",
            pipeline_status="partial_failure",
            failed_step="proposal_generation",
            completed_steps=json.dumps(["requirement_extraction"]),
            score=0, decision="NO BID",
            score_breakdown="{}", reasoning="",
        )
        db.add(rfp)
        db.commit()
    finally:
        db.close()

    # Alice tries to retry Bob's partial RFP.
    r = client.post(
        f"/api/rfps/{rfp_id}/retry",
        json={"retry_from": "proposal_generation"},
        headers=auth_headers(alice_token),
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
    print("PASS test_retry_cross_user")


# ═══════════════════════════════════════════════════════════════════════════
# Case 5: user A cannot add feedback to user B's RFP
# ═══════════════════════════════════════════════════════════════════════════
def test_feedback_cross_user():
    bob_rfp = insert_rfp(bob_id, "bob_feedback.pdf")

    r = client.post(
        f"/api/rfps/{bob_rfp}/feedback",
        json={"outcome": "won", "result_date": "2025-01-01"},
        headers=auth_headers(alice_token),
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
    print("PASS test_feedback_cross_user")


# ═══════════════════════════════════════════════════════════════════════════
# Case 6: user A cannot view feedback for user B's RFP
# ═══════════════════════════════════════════════════════════════════════════
def test_read_feedback_cross_user():
    bob_rfp = insert_rfp(bob_id, "bob_feedback_read.pdf")

    r = client.get(
        f"/api/rfps/{bob_rfp}/feedback",
        headers=auth_headers(alice_token),
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
    print("PASS test_read_feedback_cross_user")


# ═══════════════════════════════════════════════════════════════════════════
# Case 7: unauthenticated requests to protected endpoints return 403
# ═══════════════════════════════════════════════════════════════════════════
def test_no_token_returns_403():
    bob_rfp = insert_rfp(bob_id, "no_auth_test.pdf")

    assert client.get("/api/rfps").status_code == 403
    assert client.get(f"/api/rfps/{bob_rfp}").status_code == 403
    assert client.delete(f"/api/rfps/{bob_rfp}").status_code == 403
    print("PASS test_no_token_returns_403")


# ═══════════════════════════════════════════════════════════════════════════
# Case 8: owner can perform all operations on their own RFP
# ═══════════════════════════════════════════════════════════════════════════
def test_owner_can_read_and_delete():
    alice_rfp = insert_rfp(alice_id, "alice_own.pdf")

    r = client.get(f"/api/rfps/{alice_rfp}", headers=auth_headers(alice_token))
    assert r.status_code == 200

    r2 = client.delete(f"/api/rfps/{alice_rfp}", headers=auth_headers(alice_token))
    assert r2.status_code == 200

    # RFP is gone.
    r3 = client.get(f"/api/rfps/{alice_rfp}", headers=auth_headers(alice_token))
    assert r3.status_code == 404
    print("PASS test_owner_can_read_and_delete")


# ═══════════════════════════════════════════════════════════════════════════
# Case 9: analyze creates RFP owned by the authenticated user
# ═══════════════════════════════════════════════════════════════════════════
def test_analyze_assigns_owner():
    """
    Calling /api/analyze with mock pipeline assigns user_id to the created RFP.
    """
    mock_reqs = {
        "summary": "Test RFP", "client": "Agency", "budget": "$1M",
        "deadline": "2025-12-01",
        "requirements": [{"text": "Need IT services", "category": "mandatory"}],
        "keywords": ["IT"], "deliverables": [], "evaluation_criteria": [],
        "extraction_status": "complete", "confidence": "high",
        "unclear_requirements": [], "missing_information": [], "notes": None,
    }
    mock_proposal = {
        "proposal": "Our proposal", "information_gaps": [],
        "unsupported_claims_avoided": [], "evidence_used": [],
    }
    mock_score = {
        "score": 80, "decision": "BID",
        "breakdown": {"relevance_score": 80, "budget_fit": 80,
                      "requirements_match": 80, "completeness": 80},
        "reasoning": "Good fit", "weights_used": {}, "threshold_used": 60,
    }

    original_retry = main_mod._llm_with_retry
    async def fast_retry(fn, *a, max_retries=1, retry_delay=0.0, **kw):
        return await original_retry(fn, *a, max_retries=max_retries, retry_delay=0.0, **kw)

    # Patch the parse_pdf service so we don't need a real PDF file.
    with patch.object(main_mod, "parse_pdf", return_value="Sufficient RFP text content here"), \
         patch.object(main_mod, "extract_requirements", return_value=mock_reqs), \
         patch.object(main_mod, "generate_proposal", return_value=mock_proposal), \
         patch.object(main_mod, "score_bid", return_value=mock_score), \
         patch.object(main_mod, "identify_risks", return_value=[]), \
         patch.object(main_mod, "search_knowledge", return_value=[]), \
         patch.object(main_mod, "load_profile", return_value=None), \
         patch.object(main_mod, "evaluate_strategic_fit", return_value={"status": "unknown"}), \
         patch.object(main_mod, "_llm_with_retry", fast_retry):

        fake_pdf = b"%PDF-1.4 fake pdf content"
        r = client.post(
            "/api/analyze",
            files={"file": ("test.pdf", fake_pdf, "application/pdf")},
            headers=auth_headers(alice_token),
        )

    assert r.status_code == 200, r.text
    rfp_id = r.json()["id"]

    # Verify the RFP is owned by Alice via the DB.
    db = _new_db()
    try:
        rfp = db.query(RFP).filter(RFP.id == rfp_id).first()
        assert rfp is not None
        assert rfp.user_id == alice_id, \
            f"Expected user_id={alice_id}, got {rfp.user_id}"
    finally:
        db.close()

    # Bob cannot see the RFP Alice just created.
    r2 = client.get(f"/api/rfps/{rfp_id}", headers=auth_headers(bob_token))
    assert r2.status_code == 404, f"Bob should not access Alice's RFP, got {r2.status_code}"
    print("PASS test_analyze_assigns_owner")


# ── Run all ──────────────────────────────────────────────────────────────────
test_list_isolation()
test_read_cross_user()
test_delete_cross_user()
test_retry_cross_user()
test_feedback_cross_user()
test_read_feedback_cross_user()
test_no_token_returns_403()
test_owner_can_read_and_delete()
test_analyze_assigns_owner()

print("\nAll access-control tests passed.")
