import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
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
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Token:
    user = db.get(User, form_data.username) if len(form_data.username) <= 64 else None
    candidate_hash = user.password_hash if user is not None else dummy_hash
    valid_password = len(form_data.password) <= 128 and verify_password(
        form_data.password, candidate_hash
    )
    if user is None or not valid_password or not user.is_active:
        raise credentials_error()
    return Token(access_token=create_access_token(user.username))


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
