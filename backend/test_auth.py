"""
Tests for authentication: password hashing, JWT round-trip, and the
/api/auth/register + /api/auth/login HTTP endpoints.

Pattern mirrors existing test files: standalone asyncio script with
direct assertions, no pytest framework required.

Run with:
    cd backend && python test_auth.py
"""
import sys
from unittest.mock import MagicMock

# Stub modules that require native deps not available in every test env.
for _mod in ["pdfplumber", "services.parser", "services.fetcher", "services.sam_gov"]:
    sys.modules.setdefault(_mod, MagicMock())

sys.path.insert(0, ".")

# ── In-memory database ────────────────────────────────────────────────────────
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models.rfp import RFP              # noqa: F401
from models.feedback import Feedback    # noqa: F401
from models.knowledge_document import KnowledgeDocument  # noqa: F401
from models.user import User            # noqa: F401

_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=_engine)
_Session = sessionmaker(bind=_engine)

def _new_db():
    return _Session()

# ── FastAPI TestClient ────────────────────────────────────────────────────────
from fastapi.testclient import TestClient
import main as main_mod

# Override the database dependency to use the in-memory DB.
def _override_get_db():
    db = _Session()
    try:
        yield db
    finally:
        db.close()

main_mod.app.dependency_overrides[main_mod.get_db] = _override_get_db
client = TestClient(main_mod.app, raise_server_exceptions=True)


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests: password helpers and JWT
# ═══════════════════════════════════════════════════════════════════════════

def test_hash_and_verify():
    from services.auth import hash_password, verify_password
    h = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", h), "correct password should verify"
    assert not verify_password("wrong-password", h), "wrong password must not verify"
    # Two hashes of the same password must differ (bcrypt salting).
    assert hash_password("abc") != hash_password("abc"), "bcrypt must produce unique salts"
    print("PASS test_hash_and_verify")


def test_jwt_round_trip():
    from services.auth import create_access_token, decode_access_token
    token = create_access_token(user_id="user-123", email="a@example.com")
    assert isinstance(token, str) and len(token) > 20
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["email"] == "a@example.com"
    print("PASS test_jwt_round_trip")


def test_invalid_jwt_returns_none():
    from services.auth import decode_access_token
    assert decode_access_token("not.a.token") is None
    assert decode_access_token("") is None
    assert decode_access_token("eyJ.garbage.payload") is None
    print("PASS test_invalid_jwt_returns_none")


def test_tampered_jwt_returns_none():
    from services.auth import create_access_token, decode_access_token
    token = create_access_token("uid", "x@x.com")
    # Flip one character in the signature segment.
    parts = token.split(".")
    sig = parts[2]
    parts[2] = sig[:-1] + ("A" if sig[-1] != "A" else "B")
    tampered = ".".join(parts)
    assert decode_access_token(tampered) is None
    print("PASS test_tampered_jwt_returns_none")


# ═══════════════════════════════════════════════════════════════════════════
# Integration tests: HTTP endpoints
# ═══════════════════════════════════════════════════════════════════════════

def test_register_success():
    r = client.post("/api/auth/register", json={
        "email": "alice@example.com",
        "password": "securepassword1",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "alice@example.com"
    assert data["user"]["id"]
    print("PASS test_register_success")


def test_register_duplicate_email():
    client.post("/api/auth/register", json={
        "email": "bob@example.com",
        "password": "password123",
    })
    r = client.post("/api/auth/register", json={
        "email": "bob@example.com",
        "password": "password123",
    })
    assert r.status_code == 409, r.text
    print("PASS test_register_duplicate_email")


def test_register_short_password():
    r = client.post("/api/auth/register", json={
        "email": "short@example.com",
        "password": "abc",
    })
    assert r.status_code == 422, r.text
    print("PASS test_register_short_password")


def test_login_success():
    client.post("/api/auth/register", json={
        "email": "carol@example.com",
        "password": "mypassword99",
    })
    r = client.post("/api/auth/login", json={
        "email": "carol@example.com",
        "password": "mypassword99",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert data["user"]["email"] == "carol@example.com"
    print("PASS test_login_success")


def test_login_wrong_password():
    client.post("/api/auth/register", json={
        "email": "dave@example.com",
        "password": "correctpassword",
    })
    r = client.post("/api/auth/login", json={
        "email": "dave@example.com",
        "password": "wrongpassword",
    })
    assert r.status_code == 401, r.text
    print("PASS test_login_wrong_password")


def test_login_nonexistent_email():
    r = client.post("/api/auth/login", json={
        "email": "ghost@example.com",
        "password": "somepassword",
    })
    assert r.status_code == 401, r.text
    print("PASS test_login_nonexistent_email")


def test_authenticated_request_succeeds():
    """A valid Bearer token allows access to a protected endpoint."""
    r = client.post("/api/auth/register", json={
        "email": "eve@example.com",
        "password": "evesecret1",
    })
    token = r.json()["access_token"]

    r2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["email"] == "eve@example.com"
    print("PASS test_authenticated_request_succeeds")


def test_unauthenticated_request_fails():
    """Accessing a protected endpoint without a token returns 403 (HTTPBearer default)."""
    r = client.get("/api/rfps")
    # FastAPI's HTTPBearer returns 403 when no credentials header is provided.
    assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    print("PASS test_unauthenticated_request_fails")


def test_invalid_token_returns_401():
    """An invalid Bearer token returns 401."""
    r = client.get("/api/rfps", headers={"Authorization": "Bearer not.a.real.token"})
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"
    print("PASS test_invalid_token_returns_401")


def test_me_endpoint_returns_current_user():
    r = client.post("/api/auth/register", json={
        "email": "frank@example.com",
        "password": "frankpass1",
    })
    token = r.json()["access_token"]
    r2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json()["email"] == "frank@example.com"
    print("PASS test_me_endpoint_returns_current_user")


# ── Run all ──────────────────────────────────────────────────────────────────
test_hash_and_verify()
test_jwt_round_trip()
test_invalid_jwt_returns_none()
test_tampered_jwt_returns_none()
test_register_success()
test_register_duplicate_email()
test_register_short_password()
test_login_success()
test_login_wrong_password()
test_login_nonexistent_email()
test_authenticated_request_succeeds()
test_unauthenticated_request_fails()
test_invalid_token_returns_401()
test_me_endpoint_returns_current_user()

print("\nAll auth tests passed.")
