"""
Authentication and organisation isolation tests.

Run with:
    cd backend && pip install pytest httpx && pytest tests/test_auth.py -v

These are integration tests against an in-memory SQLite database.
No real Anthropic API calls are made — pipeline endpoints are not exercised here.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ── Patch DATABASE_URL before anything imports database.py ────────────────────
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_auth.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only-32chars!")

# ── App bootstrap ─────────────────────────────────────────────────────────────
from database import Base, get_db  # noqa: E402
from main import app               # noqa: E402

# Use an in-memory SQLite DB isolated per test session
TEST_DATABASE_URL = "sqlite://"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Create tables once for the whole test module."""
    # Import all models so Base.metadata knows about them
    from models.user import User              # noqa: F401
    from models.rfp import RFP               # noqa: F401
    from models.feedback import Feedback     # noqa: F401
    from models.knowledge_document import KnowledgeDocument  # noqa: F401
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def db_session():
    """Per-test DB session that rolls back after each test."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session):
    """TestClient with the DB dependency overridden to use the test session."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

def register(client: TestClient, email: str, password: str = "password123") -> dict:
    """Register a user and return the response JSON."""
    res = client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert res.status_code == 201, res.text
    return res.json()


def login(client: TestClient, email: str, password: str = "password123") -> str:
    """Return a Bearer token for the given credentials."""
    res = client.post(
        "/api/auth/token",
        data={"username": email, "password": password},
    )
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Registration tests ────────────────────────────────────────────────────────

def test_register_returns_token(client):
    data = register(client, "alice@example.com")
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["email"] == "alice@example.com"
    assert "org_id" in data
    assert "user_id" in data


def test_register_duplicate_email_rejected(client):
    register(client, "bob@example.com")
    res = client.post(
        "/api/auth/register",
        json={"email": "bob@example.com", "password": "password123"},
    )
    assert res.status_code == 409


def test_register_short_password_rejected(client):
    res = client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "password": "abc"},
    )
    assert res.status_code == 422


# ── Login tests ───────────────────────────────────────────────────────────────

def test_login_success(client):
    register(client, "carol@example.com")
    token = login(client, "carol@example.com")
    assert isinstance(token, str) and len(token) > 10


def test_login_wrong_password(client):
    register(client, "dave@example.com")
    res = client.post(
        "/api/auth/token",
        data={"username": "dave@example.com", "password": "wrongpass"},
    )
    assert res.status_code == 401


def test_login_unknown_email(client):
    res = client.post(
        "/api/auth/token",
        data={"username": "nobody@example.com", "password": "password123"},
    )
    assert res.status_code == 401


# ── /me endpoint ──────────────────────────────────────────────────────────────

def test_me_returns_user_info(client):
    data = register(client, "eve@example.com")
    token = data["access_token"]
    res = client.get("/api/auth/me", headers=auth_headers(token))
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "eve@example.com"
    assert body["org_id"] == data["org_id"]
    assert body["is_active"] is True


def test_me_without_token_returns_401(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401


def test_me_with_bad_token_returns_401(client):
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert res.status_code == 401


# ── Protected endpoint guard tests ────────────────────────────────────────────

def test_list_rfps_requires_auth(client):
    res = client.get("/api/rfps")
    assert res.status_code == 401


def test_list_rfps_with_token_returns_empty(client):
    data = register(client, "frank@example.com")
    res = client.get("/api/rfps", headers=auth_headers(data["access_token"]))
    assert res.status_code == 200
    assert res.json() == []


def test_get_rfp_requires_auth(client):
    res = client.get("/api/rfps/nonexistent-id")
    assert res.status_code == 401


# ── Organisation isolation tests ─────────────────────────────────────────────

def test_org_a_cannot_see_org_b_rfp(client, db_session):
    """
    Directly insert an RFP belonging to org B, then verify org A cannot
    fetch it — not in the list and not by direct ID.
    """
    import uuid
    import json
    from models.rfp import RFP

    # Register two users → two separate orgs
    data_a = register(client, "org_a@example.com")
    data_b = register(client, "org_b@example.com")
    token_a = data_a["access_token"]
    org_b_id = data_b["org_id"]

    # Insert an RFP owned by org B directly into the DB
    rfp_id = str(uuid.uuid4())
    rfp = RFP(
        id=rfp_id,
        filename="org_b_rfp.pdf",
        org_id=org_b_id,
        original_text="test",
        pipeline_status="completed",
        completed_steps=json.dumps(["requirement_extraction", "proposal_generation", "bid_scoring"]),
        score=80,
        decision="BID",
        score_breakdown="{}",
        reasoning="",
        requirements="{}",
        risks="[]",
        strategic_fit="{}",
        knowledge_refs="[]",
        grounding_report="{}",
    )
    db_session.add(rfp)
    db_session.commit()

    # Org A's list should be empty (no org A RFPs exist)
    list_res = client.get("/api/rfps", headers=auth_headers(token_a))
    assert list_res.status_code == 200
    assert all(r["id"] != rfp_id for r in list_res.json()), \
        "Org A should not see org B's RFP in the list"

    # Org A cannot fetch org B's RFP by direct ID
    get_res = client.get(f"/api/rfps/{rfp_id}", headers=auth_headers(token_a))
    assert get_res.status_code == 404, \
        "Org A should receive 404, not 200, when fetching org B's RFP"


def test_org_a_can_see_own_rfp(client, db_session):
    """Org A can read its own RFP by direct ID."""
    import uuid
    import json
    from models.rfp import RFP

    data_a = register(client, "own_rfp@example.com")
    token_a = data_a["access_token"]
    org_a_id = data_a["org_id"]

    rfp_id = str(uuid.uuid4())
    rfp = RFP(
        id=rfp_id,
        filename="my_rfp.pdf",
        org_id=org_a_id,
        original_text="test",
        pipeline_status="completed",
        completed_steps=json.dumps(["requirement_extraction", "proposal_generation", "bid_scoring"]),
        score=75,
        decision="BID",
        score_breakdown="{}",
        reasoning="",
        requirements="{}",
        risks="[]",
        strategic_fit="{}",
        knowledge_refs="[]",
        grounding_report="{}",
    )
    db_session.add(rfp)
    db_session.commit()

    # Should appear in list
    list_res = client.get("/api/rfps", headers=auth_headers(token_a))
    assert list_res.status_code == 200
    assert any(r["id"] == rfp_id for r in list_res.json())

    # Should be readable by direct ID
    get_res = client.get(f"/api/rfps/{rfp_id}", headers=auth_headers(token_a))
    assert get_res.status_code == 200
    assert get_res.json()["id"] == rfp_id


def test_feedback_isolation(client, db_session):
    """Org A cannot add feedback to org B's RFP."""
    import uuid
    import json
    from models.rfp import RFP

    data_a = register(client, "fb_a@example.com")
    data_b = register(client, "fb_b@example.com")
    token_a = data_a["access_token"]
    org_b_id = data_b["org_id"]

    # Create an RFP owned by org B
    rfp_id = str(uuid.uuid4())
    rfp = RFP(
        id=rfp_id,
        filename="fb_test.pdf",
        org_id=org_b_id,
        original_text="test",
        pipeline_status="completed",
        completed_steps=json.dumps(["requirement_extraction", "proposal_generation", "bid_scoring"]),
        score=70,
        decision="BID",
        score_breakdown="{}",
        reasoning="",
        requirements="{}",
        risks="[]",
        strategic_fit="{}",
        knowledge_refs="[]",
        grounding_report="{}",
    )
    db_session.add(rfp)
    db_session.commit()

    # Org A should get 404 when posting feedback to org B's RFP
    res = client.post(
        f"/api/rfps/{rfp_id}/feedback",
        json={"outcome": "won", "result_date": "2025-01-01"},
        headers=auth_headers(token_a),
    )
    assert res.status_code == 404
