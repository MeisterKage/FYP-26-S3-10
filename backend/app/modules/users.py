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
    UserCategoryPreference, UserCountryPreference, utcnow,
)
from ..countries import normalise
from ..sanitize import clean_plain_text
from ..security import login_required, roles_required
from ..validation import json_body, require_str

bp = Blueprint("users", __name__)

#: The toggles listed in PDD Figure 5.13.
NOTIFICATION_EVENTS = (
    "breaking_news",
    "comment_reply",
    "followed_contributor_article",
    #Was "weekly_digest", which nothing ever sent. Monthly digests replaced it.
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

    if "countryCodes" in data:
        codes = data["countryCodes"] or []
        if not isinstance(codes, list):
            raise ApiError("Countries must be a list.", status=422, field="countryCodes")
        try:
            wanted = {normalise(c) for c in codes} - {None}
        except ValueError:
            raise ApiError("One of those is not a country.", status=422, field="countryCodes")
        UserCountryPreference.query.filter_by(user_id=user.id).delete()
        for code in sorted(wanted):
            db.session.add(UserCountryPreference(user_id=user.id, country_code=code))

    db.session.commit()
    return jsonify({"message": "Profile updated."})


#--------------------------------------------------------------------------- #
# Following a section or a country, one at a time (the follow buttons)
#--------------------------------------------------------------------------- #

def _interests(user) -> dict:
    return {
        "categoryIds": [
            p.category_id for p in UserCategoryPreference.query.filter_by(user_id=user.id)
        ],
        "countryCodes": sorted(
            p.country_code for p in UserCountryPreference.query.filter_by(user_id=user.id)
        ),
    }


def _followable_category(category_id: int) -> Category:
    #Uncategorised only holds articles whose section was deleted: not a topic.
    category = Category.query.filter_by(id=category_id, deleted_at=None, is_system=False).first()
    if category is None:
        raise ApiError("That section was not found.", status=404)
    return category


def _followable_country(code: str) -> str:
    try:
        normalised = normalise(code)
    except ValueError:
        normalised = None
    if not normalised:
        raise ApiError("That country was not found.", status=404)
    return normalised


@bp.put("/me/interests/categories/<int:category_id>")
@login_required
def follow_category(category_id: int):
    """Follow a section: its articles join your front page."""
    user = g.current_user
    category = _followable_category(category_id)
    if not UserCategoryPreference.query.filter_by(user_id=user.id, category_id=category.id).first():
        db.session.add(UserCategoryPreference(user_id=user.id, category_id=category.id))
        db.session.commit()
    return jsonify(_interests(user))


@bp.delete("/me/interests/categories/<int:category_id>")
@login_required
def unfollow_category(category_id: int):
    user = g.current_user
    UserCategoryPreference.query.filter_by(user_id=user.id, category_id=category_id).delete()
    db.session.commit()
    return jsonify(_interests(user))


@bp.put("/me/interests/countries/<code>")
@login_required
def follow_country(code: str):
    """Follow a country: its articles join your front page."""
    user = g.current_user
    country = _followable_country(code)
    if not UserCountryPreference.query.filter_by(user_id=user.id, country_code=country).first():
        db.session.add(UserCountryPreference(user_id=user.id, country_code=country))
        db.session.commit()
    return jsonify(_interests(user))


@bp.delete("/me/interests/countries/<code>")
@login_required
def unfollow_country(code: str):
    user = g.current_user
    country = _followable_country(code)
    UserCountryPreference.query.filter_by(user_id=user.id, country_code=country).delete()
    db.session.commit()
    return jsonify(_interests(user))


@bp.get("/me/notification-preferences")
@login_required
def get_notification_preferences():
    stored = {
        p.event_type: p.enabled
        for p in NotificationPreference.query.filter_by(user_id=g.current_user.id)
    }
    #An unset toggle defaults to on, so a new account is not silently muted.
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
