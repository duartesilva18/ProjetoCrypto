"""JWT authentication for the dashboard API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import get_settings

_ALGORITHM = "HS256"
_TOKEN_EXPIRE_HOURS = 24

security = HTTPBearer(auto_error=False)


def create_access_token(subject: str = "dashboard") -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(hours=_TOKEN_EXPIRE_HOURS)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def verify_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


async def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict:
    """FastAPI dependency that enforces JWT auth on protected routes."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )
    return verify_token(credentials.credentials)


AuthDep = Annotated[dict, Depends(require_auth)]
