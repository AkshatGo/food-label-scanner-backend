"""Auth service: signup/login with JWT bearer tokens.

Passwords hashed with PBKDF2 (hashlib, no native deps). Tokens carry the
user_id and expiry. Health-condition profile is restricted to the 4
supported values (ADR-4: no free-text disease entry).
"""

import hashlib
import hmac
import secrets
import re
from datetime import datetime, timedelta, timezone

import jwt

from .. import config
from ..database import store

PASSWORD_SALT_BYTES = 16
PASSWORD_ITERATIONS = 120_000


class AuthError(Exception):
    def __init__(self, code, message, http_status):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def _hash_password(password, salt=None):
    salt = salt or secrets.token_hex(PASSWORD_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_ITERATIONS
    ).hex()
    return f"{salt}${digest}"


def _verify_password(password, stored):
    try:
        salt, _digest = stored.split("$", 1)
    except ValueError:
        return False
    expected = _hash_password(password, salt)
    return hmac.compare_digest(expected, stored)


def _issue_token(user_id):
    user = store.users.find_one({"user_id": user_id}) or {}
    payload = {
        "sub": user_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=config.JWT_EXPIRY_HOURS),
        "ver": user.get("token_version", 0),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def signup(email, password):
    if not isinstance(email, str) or len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()):
        raise AuthError("VALIDATION_ERROR", "A valid email is required", 400)
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise AuthError("VALIDATION_ERROR", "Password must be at least 8 characters", 400)

    email = email.strip().lower()
    if store.users.find_one({"email": email}):
        raise AuthError("CONFLICT", "An account with this email already exists", 409)

    user_id = f"u_{secrets.token_hex(8)}"
    user = {
        "user_id": user_id,
        "email": email,
        "auth_hash": _hash_password(password),
        "conditions": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    from pymongo.errors import DuplicateKeyError
    try:
        store.users.insert_one(user)
    except DuplicateKeyError as error:
        raise AuthError("CONFLICT", "An account with this email already exists", 409) from error
    return {"user_id": user_id, "token": _issue_token(user_id)}


def login(email, password):
    if not isinstance(email, str) or not isinstance(password, str) or not email or not password or len(password) > 128:
        raise AuthError("VALIDATION_ERROR", "Email and password are required", 400)

    user = store.users.find_one({"email": email.strip().lower()})
    if not user or not _verify_password(password, user.get("auth_hash", "")):
        raise AuthError("UNAUTHORIZED", "Invalid email or password", 401)

    return {"user_id": user["user_id"], "token": _issue_token(user["user_id"])}


def user_from_token(token):
    """Resolve a bearer token to a user document; raises AuthError on failure."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as error:
        raise AuthError("UNAUTHORIZED", "Token expired", 401) from error
    except jwt.InvalidTokenError as error:
        raise AuthError("UNAUTHORIZED", "Invalid token", 401) from error

    user = store.users.find_one({"user_id": payload.get("sub")})
    if not user:
        raise AuthError("UNAUTHORIZED", "User no longer exists", 401)
    if payload.get("ver", 0) != user.get("token_version", 0):
        raise AuthError("UNAUTHORIZED", "Session expired. Please sign in again.", 401)
    return user


def update_conditions(user_id, conditions):
    from .personalization import SUPPORTED_CONDITIONS

    if not isinstance(conditions, list):
        raise AuthError("VALIDATION_ERROR", "conditions must be a list", 400)
    if not all(isinstance(c, str) for c in conditions):
        raise AuthError("VALIDATION_ERROR", "conditions must contain strings", 400)
    invalid = [c for c in conditions if c not in SUPPORTED_CONDITIONS]
    if invalid:
        raise AuthError(
            "INVALID_CONDITION",
            f"Unsupported condition(s): {', '.join(invalid)}. "
            f"Supported: {', '.join(SUPPORTED_CONDITIONS)}",
            422,
        )

    unique = sorted(set(conditions))
    store.users.update_one(
        {"user_id": user_id},
        {"$set": {"conditions": unique}},
    )
    return {"user_id": user_id, "conditions": unique}


def get_user_conditions(user_id):
    user = store.users.find_one({"user_id": user_id})
    if not user:
        raise AuthError("NOT_FOUND", "User not found", 404)
    return {"user_id": user_id, "conditions": user.get("conditions", [])}
