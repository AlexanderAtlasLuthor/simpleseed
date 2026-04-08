"""
Authentication utilities: password hashing and JWT creation/validation.

Environment variables consumed:
  JWT_SECRET_KEY  – secret used to sign/verify JWTs (MUST be changed in production)
  JWT_ALGORITHM   – JWT signing algorithm, default HS256
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

# ── Configuration ──────────────────────────────────────────────────────────────
SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_insecure_dev_secret_key_32chars!!")
ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
# Token valid for 24 hours; refresh by re-authenticating.
ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

# bcrypt is intentionally the only scheme; no deprecated fallback.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password*."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if *plain_password* matches *hashed_password*."""
    return _pwd_context.verify(plain_password, hashed_password)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(user_id: str, email: str) -> str:
    """
    Create a signed JWT for the given user.

    The token contains:
      sub   – user UUID (used to look up the user on every request)
      email – included for convenience; authoritative source is the DB
      exp   – expiration timestamp
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT.

    Returns the payload dict on success, or None if the token is invalid,
    expired, or tampered with.  Never raises — callers check for None.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # Require "sub" to be present; malformed tokens without it are rejected.
        if not payload.get("sub"):
            return None
        return payload
    except JWTError:
        return None
