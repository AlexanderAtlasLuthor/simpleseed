"""
Authentication endpoints:
  POST /api/auth/register  — create account (email + password → JWT)
  POST /api/auth/token     — OAuth2 password flow login → JWT
  GET  /api/auth/me        — return current user info (requires JWT)
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from services.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Request / Response schemas ────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    org_id: str
    email: str


class UserResponse(BaseModel):
    id: str
    email: str
    org_id: str
    is_active: bool
    created_at: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """
    Create a new user account.

    - email must be unique across the system
    - password is bcrypt-hashed before storage
    - org_id is auto-generated (uuid4); the new user is the sole member of
      their organisation.  Invite flows can later share an org_id.
    - Returns a JWT so the client is logged in immediately after registration.
    """
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email address already exists.",
        )

    user_id = str(uuid.uuid4())
    org_id  = str(uuid.uuid4())   # each new account gets its own organisation
    user = User(
        id=user_id,
        email=body.email,
        hashed_password=hash_password(body.password),
        org_id=org_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user_id=user.id, org_id=user.org_id)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        org_id=user.org_id,
        email=user.email,
    )


@router.post("/token", response_model=TokenResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session  = Depends(get_db),
):
    """
    OAuth2 password-flow login.

    Accepts application/x-www-form-urlencoded with fields:
      username  (treated as email address)
      password

    Returns a Bearer JWT.
    """
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled.",
        )

    token = create_access_token(user_id=user.id, org_id=user.org_id)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        org_id=user.org_id,
        email=user.email,
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        org_id=current_user.org_id,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat() if current_user.created_at else "",
    )
