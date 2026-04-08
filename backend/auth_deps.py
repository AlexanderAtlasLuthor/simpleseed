"""
FastAPI dependency: get_current_user

Usage in route handlers:

    from auth_deps import get_current_user
    from models.user import User

    @app.get("/api/rfps")
    def list_rfps(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        ...
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from services.auth import decode_access_token

# HTTPBearer extracts the token from the "Authorization: Bearer <token>" header.
# auto_error=True means FastAPI raises an HTTPException when the header is
# missing or malformed (behavior may vary by FastAPI version: 401 or 403).
_bearer = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """
    Validate the Bearer token and return the corresponding User row.

    Raises HTTP 401 if:
      - the token is missing, expired, or tampered with
      - the user referenced by the token no longer exists in the DB

    This dependency is injected into every protected route.
    """
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload["sub"]
    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        # Token was valid but the account has been deleted — treat as 401.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
