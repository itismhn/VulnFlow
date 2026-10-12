import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_COOKIE = "rm_access"
REFRESH_COOKIE = "rm_refresh"
CSRF_COOKIE = "rm_csrf"
CSRF_HEADER = "X-CSRF-Token"

_hasher = PasswordHasher()
# Used to keep login timing constant when the username does not exist
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < settings.password_min_length:
        problems.append(f"must be at least {settings.password_min_length} characters")
    if not any(c.islower() for c in password):
        problems.append("must contain a lowercase letter")
    if not any(c.isupper() for c in password):
        problems.append("must contain an uppercase letter")
    if not any(c.isdigit() for c in password):
        problems.append("must contain a digit")
    if not any(not c.isalnum() for c in password):
        problems.append("must contain a symbol")
    return problems


def create_token(subject: str, kind: str, expires: timedelta, **claims: Any) -> str:
    now = datetime.now(UTC)
    payload = {"sub": subject, "type": kind, "iat": now, "exp": now + expires, **claims}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str, kind: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    return payload if payload.get("type") == kind else None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)
