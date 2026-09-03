"""Authentication and Role Management (PDD Section 2.2).

Covers PDD Figures 5.1 (Register), 5.9 (Login), 5.10 (Logout), 5.11 (Reset Password).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, g, jsonify, request

from ..enums import Role
from ..errors import ApiError
from ..extensions import db
from ..integrations import email_service
from ..models import (
    AuditLog, Category, PasswordResetToken, User, UserCategoryPreference, utcnow,
)
from ..sanitize import clean_plain_text
from ..security import (
    hash_password, hash_reset_token, issue_access_token, login_required,
    new_reset_token, reset_tokens_match, validate_password_strength, verify_password,
)
from ..ratelimit import (
    LOGIN_LIMIT, REGISTER_LIMIT, RESET_LIMIT, client_address, limiter,
)
from ..validation import json_body, require_id_list

bp = Blueprint("auth", __name__)


def _serialize(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "displayName": user.display_name,
        "role": user.role.value,
        "bio": user.bio,
        "accuracyRate": user.accuracy_rate,
        "hasPremiumAccess": user.has_premium_access(),
    }


def _audit(action: str, **kwargs) -> None:
    db.session.add(
        AuditLog(
            actor_id=getattr(g.get("current_user"), "id", None),
            action=action,
            ip_address=request.remote_addr,
            **kwargs,
        )
    )


@bp.post("/auth/register")
@limiter.limit(REGISTER_LIMIT, key_func=client_address)
def register():
    """PDD Figure 5.1. Creates a Free Registered User and signs them in at once."""
    data = json_body()

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    display_name = clean_plain_text(data.get("displayName") or "")
    # A bare string here used to reach SQLAlchemy's IN clause and raise a 500.
    category_ids = require_id_list(data, "categoryIds", max_items=50)

    if not email or "@" not in email:
        raise ApiError("Enter a valid email address.", status=422, field="email")
    if not display_name:
        raise ApiError("Enter your name.", status=422, field="displayName")
    validate_password_strength(password)

    if User.query.filter_by(email=email).first():
        # PDD Figure 5.1: duplicate email rejected with a pointer to the login page.
        raise ApiError(
            "An account with this email already exists. Try signing in instead.",
            status=409, field="email",
        )

    user = User(
        email=email,
        display_name=display_name,
        password_hash=hash_password(password),
        role=Role.FREE_REGISTERED,
    )
    db.session.add(user)
    db.session.flush()

    valid_ids = {
        c.id for c in Category.query.filter(
            Category.id.in_(category_ids), Category.deleted_at.is_(None)
        )
    }
    for category_id in valid_ids:
        db.session.add(UserCategoryPreference(user_id=user.id, category_id=category_id))

    _audit("user.register", entity_type="user", entity_id=user.id)
    db.session.commit()

    return jsonify({"user": _serialize(user), "token": issue_access_token(user)}), 201


@bp.post("/auth/login")
@limiter.limit(LOGIN_LIMIT)
def login():
    """PDD Figure 5.9."""
    data = json_body()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()

    # One message for both failure modes, so the form cannot enumerate accounts.
    invalid = ApiError("Invalid username or password.", status=401)
    if user is None or user.deleted_at is not None:
        raise invalid
    if not verify_password(user.password_hash, password):
        raise invalid
    if user.is_suspended:
        raise ApiError(
            user.suspended_reason or "This account is suspended.", status=403
        )

    return jsonify({"user": _serialize(user), "token": issue_access_token(user)})


@bp.post("/auth/logout")
@login_required
def logout():
    """PDD Figure 5.10.

    Tokens are stateless and short-lived, so the server has nothing to revoke;
    the client discards it. A token denylist would be the next step if the
    security review calls for immediate revocation.
    """
    return jsonify({"message": "You have been signed out."})


@bp.get("/auth/me")
@login_required
def me():
    return jsonify({"user": _serialize(g.current_user)})


@bp.post("/auth/password-reset/request")
@limiter.limit(RESET_LIMIT)
def request_password_reset():
    """PDD Figure 5.11.

    An unregistered email fails silently with the same confirmation, so the form
    cannot be used to discover which addresses have accounts.
    """
    data = json_body()
    email = (data.get("email") or "").strip().lower()

    confirmation = jsonify(
        {"message": "If that email is registered, a reset link is on its way."}
    )

    user = User.query.filter_by(email=email, deleted_at=None).first()
    if user is None:
        return confirmation

    raw, token_hash = new_reset_token()
    ttl = current_app.config["RESET_TOKEN_TTL_MINUTES"]
    db.session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl),
        )
    )
    db.session.commit()

    email_service.send(
        to=user.email,
        subject="Reset your password",
        body=f"Use this link within {ttl} minutes: /reset-password?token={raw}",
    )
    return confirmation


@bp.post("/auth/password-reset/confirm")
@limiter.limit(RESET_LIMIT)
def confirm_password_reset():
    data = json_body()
    raw = data.get("token") or ""
    password = data.get("password") or ""

    validate_password_strength(password)

    record = PasswordResetToken.query.filter_by(token_hash=hash_reset_token(raw)).first()

    expired = ApiError("This reset link has expired. Request a new one.", status=400)
    if record is None or record.used_at is not None:
        raise expired
    if record.expires_at <= datetime.now(timezone.utc):
        raise expired
    if not reset_tokens_match(record.token_hash, raw):
        raise expired

    user = User.query.get(record.user_id)
    user.password_hash = hash_password(password)
    record.used_at = utcnow()

    _audit("user.password_reset", entity_type="user", entity_id=user.id)
    db.session.commit()

    return jsonify({"message": "Password updated. You can sign in now."})
