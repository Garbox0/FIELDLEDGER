import os
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import Lock

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppRole, User
from app.schemas import Token, UserRead


router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
password_hash = PasswordHash.recommended()
dummy_hash = password_hash.hash("fieldledger-dummy-password-never-used")
_login_failures: dict[str, deque[float]] = {}
_login_failures_lock = Lock()


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET must contain at least 32 characters")
    return secret


def create_access_token(username: str) -> str:
    minutes = int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "60"))
    expires_at = datetime.now(UTC) + timedelta(minutes=minutes)
    return jwt.encode(
        {"sub": username, "exp": expires_at}, jwt_secret(), algorithm="HS256"
    )


def credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def public_demo_enabled() -> bool:
    return os.getenv("PUBLIC_DEMO_VIEWER", "false").lower() == "true"


def login_client(request: Request) -> str:
    if os.getenv("TRUST_CF_CONNECTING_IP", "false").lower() == "true":
        cloudflare_ip = request.headers.get("CF-Connecting-IP")
        if cloudflare_ip:
            return cloudflare_ip[:64]
    return request.client.host if request.client else "unknown"


def enforce_login_rate_limit(client: str) -> None:
    limit = max(1, int(os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "10")))
    window = max(1, int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60")))
    now = time.monotonic()
    with _login_failures_lock:
        failures = _login_failures.setdefault(client, deque())
        while failures and failures[0] <= now - window:
            failures.popleft()
        if len(failures) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts",
                headers={"Retry-After": str(window)},
            )


def record_login_failure(client: str) -> None:
    with _login_failures_lock:
        _login_failures.setdefault(client, deque()).append(time.monotonic())


def clear_login_failures(client: str) -> None:
    with _login_failures_lock:
        _login_failures.pop(client, None)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=["HS256"])
        username = payload.get("sub")
        if not isinstance(username, str):
            raise credentials_error()
    except InvalidTokenError as exc:
        raise credentials_error() from exc

    user = db.get(User, username)
    if user is None or not user.is_active:
        raise credentials_error()
    return user


def require_roles(*roles: AppRole) -> Callable[..., User]:
    def authorize(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role is not allowed to perform this action",
            )
        return current_user

    return authorize


@router.post("/login", response_model=Token)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    client = login_client(request)
    enforce_login_rate_limit(client)
    user = db.get(User, form_data.username) if len(form_data.username) <= 64 else None
    candidate_hash = user.password_hash if user is not None else dummy_hash
    valid_password = len(form_data.password) <= 128 and verify_password(
        form_data.password, candidate_hash
    )
    if user is None or not valid_password or not user.is_active:
        record_login_failure(client)
        raise credentials_error()
    clear_login_failures(client)
    return Token(access_token=create_access_token(user.username))


@router.get("/demo", include_in_schema=False)
def demo_status() -> dict[str, bool]:
    return {"enabled": public_demo_enabled()}


@router.post("/demo", response_model=Token, include_in_schema=False)
def demo_login(db: Session = Depends(get_db)) -> Token:
    if not public_demo_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    viewer = db.get(User, "viewer")
    if viewer is None or not viewer.is_active or viewer.role != AppRole.VIEWER:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Token(access_token=create_access_token(viewer.username))


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
