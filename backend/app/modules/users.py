"""User and Account Service (PDD Section 3).

Profile, preferences, and the contributor application.
Covers PDD Figures 5.12, 5.13, 5.15.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..enums import ApplicationStatus, Role
from ..errors import ApiError
from ..extensions import db
from ..models import (
    Category, ContributorApplication, NotificationPreference,
    UserCategoryPreference, utcnow,
)
from ..sanitize import clean_plain_text
from ..security import login_required, roles_required
from ..validation import json_body, require_str

bp = Blueprint("users", __name__)

#: The toggles listed in PDD Figure 5.13.
NOTIFICATION_EVENTS = (
    "breaking_news",
    "comment_reply",
    "followed_contributor_article",
    # Was "weekly_digest", which nothing ever sent. Monthly digests replaced it.
    "monthly_digest",
    "account_security",
)


@bp.patch("/me")
@login_required
def update_profile():
    """PDD Figure 5.12. Saving refreshes the personalised feed immediately."""
    data = json_body()
    user = g.current_user

    if "displayName" in data:
        name = clean_plain_text(data["displayName"])
        if not name:
            raise ApiError("Your name cannot be empty.", status=422, field="displayName")
        user.display_name = name
    if "bio" in data:
        user.bio = clean_plain_text(data["bio"])[:2000] or None

    if "categoryIds" in data:
        UserCategoryPreference.query.filter_by(user_id=user.id).delete()
        valid = Category.query.filter(
            Category.id.in_(data["categoryIds"] or []), Category.deleted_at.is_(None)
        )
        for category in valid:
            db.session.add(
                UserCategoryPreference(user_id=user.id, category_id=category.id)
            )

    db.session.commit()
    return jsonify({"message": "Profile updated."})


@bp.get("/me/notification-preferences")
@login_required
def get_notification_preferences():
    stored = {
        p.event_type: p.enabled
        for p in NotificationPreference.query.filter_by(user_id=g.current_user.id)
    }
    # An unset toggle defaults to on, so a new account is not silently muted.
    return jsonify(
        {"preferences": {event: stored.get(event, True) for event in NOTIFICATION_EVENTS}}
    )


@bp.put("/me/notification-preferences")
@login_required
def set_notification_preferences():
    """PDD Figure 5.13. Applies to future triggers only; nothing is sent retroactively."""
    data = json_body()
    prefs = data.get("preferences") or {}

    for event, enabled in prefs.items():
        if event not in NOTIFICATION_EVENTS:
            raise ApiError(f"Unknown notification type '{event}'.", status=422)

        row = NotificationPreference.query.filter_by(
            user_id=g.current_user.id, event_type=event
        ).first()
        if row is None:
            row = NotificationPreference(user_id=g.current_user.id, event_type=event)
            db.session.add(row)
        row.enabled = bool(enabled)

    db.session.commit()
    return jsonify({"message": "Notification settings saved."})


@bp.post("/me/contributor-application")
@roles_required(Role.FREE_REGISTERED, Role.PREMIUM_REGISTERED)
def apply_to_contribute():
    """PDD Figure 5.15. Goes to an administrator; never grants access immediately."""
    data = json_body()

    sample = clean_plain_text(data.get("writingSample") or "")
    if len(sample) < 200:
        raise ApiError(
            "Include a writing sample of at least 200 characters.",
            status=422, field="writingSample",
        )

    existing = ContributorApplication.query.filter_by(user_id=g.current_user.id).first()
    if existing:
        if existing.status == ApplicationStatus.PENDING:
            raise ApiError("Your application is already under review.", status=409)
        if existing.reapply_after and existing.reapply_after > utcnow():
            raise ApiError(
                f"You can reapply after {existing.reapply_after.date().isoformat()}.",
                status=409,
            )
        db.session.delete(existing)
        db.session.flush()

    db.session.add(
        ContributorApplication(
            user_id=g.current_user.id,
            writing_sample=sample,
            background=clean_plain_text(data.get("background") or "") or None,
        )
    )
    db.session.commit()

    return jsonify({"message": "Application submitted for review."}), 201


@bp.get("/me/contributor-application")
@login_required
def my_application():
    application = ContributorApplication.query.filter_by(user_id=g.current_user.id).first()
    if application is None:
        return jsonify({"application": None})

    return jsonify(
        {
            "application": {
                "status": application.status.value,
                "reason": application.decision_reason,
                "reapplyAfter": application.reapply_after.isoformat()
                if application.reapply_after
                else None,
                "submittedAt": application.created_at.isoformat(),
            }
        }
    )
