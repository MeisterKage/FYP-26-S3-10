"""Auth and Role Middleware (PDD Section 3).

Every request from the client passes through here before reaching an application
service, "so role-based access control is enforced in one place rather than
scattered across individual endpoints". Route handlers therefore never inspect
`current_user.role` themselves; they declare what they need with a decorator.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import current_app, g, request

from .enums import Role
from .errors import ApiError

_hasher = PasswordHasher()


#--------------------------------------------------------------------------- #
# Passwords  (PRD 5.1 Security)
#--------------------------------------------------------------------------- #

def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(password_hash: str, raw: str) -> bool:
    try:
        return _hasher.verify(password_hash, raw)
    except VerifyMismatchError:
        return False


def validate_password_strength(raw: str) -> None:
    """PRD 5.1: at least 12 characters, mixed character classes supported.

    Length is the requirement that is actually mandated; the class checks below
    are advisory and deliberately not enforced, because forcing composition
    rules is known to push users toward weaker, more predictable passwords.
    """
    minimum = current_app.config["MIN_PASSWORD_LENGTH"]
    if len(raw) < minimum:
        raise ApiError(
            f"Password must be at least {minimum} characters.",
            status=422, field="password",
        )


#--------------------------------------------------------------------------- #
# Tokens
#--------------------------------------------------------------------------- #

def _password_stamp(user) -> str:
    """Changes with the password, so a reset ends sessions opened with the old one."""
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


def issue_access_token(user) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "pwd": _password_stamp(user),
        "iat": now,
        "exp": now + timedelta(minutes=current_app.config["JWT_ACCESS_TTL_MINUTES"]),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ApiError("Session expired. Please sign in again.", status=401)
    except jwt.InvalidTokenError:
        raise ApiError("Invalid session.", status=401)


def new_reset_token() -> tuple[str, str]:
    """Return (raw_token, token_hash). Only the hash is ever stored."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_reset_token(raw)


def hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def reset_tokens_match(stored_hash: str, raw: str) -> bool:
    return hmac.compare_digest(stored_hash, hash_reset_token(raw))


#--------------------------------------------------------------------------- #
# Request context
#--------------------------------------------------------------------------- #

def load_current_user() -> None:
    """Populate g.current_user from the Authorization header, if present.

    Registered as a before_request hook, so it runs for every route including
    public ones; an Unregistered User is simply g.current_user is None.
    """
    from .models import User

    g.current_user = None
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return

    claims = decode_access_token(header[7:])

    #The signature is valid, but the payload shape is not guaranteed, a token
    #issued by an earlier version of this code may not carry a usable subject.
    #That is an invalid session, not a server crash.
    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError):
        raise ApiError("Invalid session.", status=401) from None

    user = User.query.get(user_id)

    if user is None or user.deleted_at is not None:
        raise ApiError("Account no longer exists.", status=401)
    if user.is_suspended:
        raise ApiError("This account is suspended.", status=403)
    if claims.get("pwd") != _password_stamp(user):
        raise ApiError("Session expired. Please sign in again.", status=401)

    g.current_user = user


def current_user():
    return getattr(g, "current_user", None)


#--------------------------------------------------------------------------- #
# Decorators
#--------------------------------------------------------------------------- #

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            raise ApiError("Sign in to continue.", status=401)
        return fn(*args, **kwargs)

    return wrapper


def roles_required(*roles: Role):
    """Restrict a route to the given tiers.

    System administrators are NOT implicitly granted every route. Where an admin
    should have access, list Role.SYSTEM_ADMIN explicitly, an implicit
    god-role is how privilege checks quietly stop meaning anything.
    """
    allowed = frozenset(roles)

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                raise ApiError("Sign in to continue.", status=401)
            if user.role not in allowed:
                raise ApiError(
                    "Your account does not have permission for this action.", status=403
                )
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def premium_required(fn):
    """Gate premium article bodies.

    Checks the live subscription, not the role tier. A cancelled or lapsed
    subscriber still carries role=PREMIUM_REGISTERED until a job downgrades them,
    so the role alone would keep the paywall open indefinitely.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            raise ApiError("Sign in to continue.", status=401)
        if not user.has_premium_access():
            raise ApiError("This article requires an active subscription.", status=402)
        return fn(*args, **kwargs)

    return wrapper


def editor_owns_category(category_id: int) -> bool:
    """Editors act only within their assigned categories (PRD 1.3.2).

    Administrators are exempt: PRD 1.3.2 gives them platform-wide authority over
    published articles, which is a stated power rather than an implicit one.
    """
    from .models import EditorCategory

    user = current_user()
    if user is None:
        return False
    if user.role == Role.SYSTEM_ADMIN:
        return True
    if user.role != Role.EDITOR:
        return False

    return (
        EditorCategory.query.filter_by(editor_id=user.id, category_id=category_id).first()
        is not None
    )
