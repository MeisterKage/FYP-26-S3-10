"""Administration (PDD Figures 5.51-5.62).

Account governance, contributor applications, categories, platform-wide
thresholds, dashboard, and logs. Every route is administrator-only and audited.
"""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

from ..credibility import DEFAULTS
from ..enums import ApplicationStatus, ArticleStatus, ReportStatus, Role
from ..errors import ApiError
from ..extensions import db
from ..models import (
    Article, AuditLog, Category, ContributorApplication, EditorCategory, Notification,
    PlatformSetting, Report, User, utcnow,
)
from ..sanitize import clean_plain_text
from ..scoring_service import rescore_contributor_articles
from ..security import roles_required
from ..validation import (
    json_body, require_choice, require_id_list, require_int, require_number, require_str,
)
from .articles import slugify

bp = Blueprint("admin", __name__)

admin_only = roles_required(Role.SYSTEM_ADMIN)

#: Upper bound on any tunable threshold. Nothing in the formula stays meaningful
#: past this, and the cap keeps a typo ("1000" for "100") from flattening every
#: score against the clamp.
SETTING_CEILING = 1000.0


def _audit(action: str, entity_type: str, entity_id: int, detail: str | None = None):
    db.session.add(
        AuditLog(
            actor_id=g.current_user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
            ip_address=request.remote_addr,
        )
    )


# --------------------------------------------------------------------------- #
#  Users  (PDD Figures 5.51-5.53, 5.56)
# --------------------------------------------------------------------------- #

@bp.get("/admin/users")
@admin_only
def list_users():
    q = (request.args.get("q") or "").strip()
    role = request.args.get("role")

    query = User.query.filter(User.deleted_at.is_(None))
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(User.email.ilike(like), User.display_name.ilike(like))
        )
    if role:
        try:
            query = query.filter(User.role == Role(role))
        except ValueError:
            raise ApiError(f"Unknown role '{role}'.", status=422, field="role")

    users = query.order_by(User.created_at.desc()).limit(100).all()
    return jsonify(
        {
            "users": [
                {
                    "id": u.id,
                    "email": u.email,
                    "name": u.display_name,
                    "role": u.role.value,
                    "suspended": u.is_suspended,
                    "accuracyRate": u.accuracy_rate,
                    "joinedAt": u.created_at.isoformat(),
                }
                for u in users
            ]
        }
    )


@bp.post("/admin/users/<int:user_id>/suspend")
@admin_only
def toggle_suspension(user_id: int):
    """PDD Figure 5.52. Suspension is reversible and destroys nothing."""
    user = _target_user(user_id)
    data = json_body()
    suspend = bool(data.get("suspend", True))

    user.is_suspended = suspend
    user.suspended_reason = clean_plain_text(data.get("reason") or "") or None if suspend else None

    _audit("user.suspend" if suspend else "user.unsuspend", "user", user.id,
           user.suspended_reason)
    db.session.commit()
    return jsonify({"suspended": user.is_suspended})


@bp.delete("/admin/users/<int:user_id>")
@admin_only
def delete_user(user_id: int):
    """PDD Figure 5.87. Soft delete, with a choice about the person's articles.

    Credentials are scrubbed and the account is unusable either way. What
    happens to anything they published is the administrator's call:

      keep    (default) articles stay live under an "Account Removed" byline,
              so the platform's accountability record survives the account
      remove  articles are unpublished, which retains the revision and
              correction history rather than destroying it

    Nothing here hard-deletes an article. A published piece that has been
    corrected is part of the record of those corrections, and removing the row
    would take the evidence with it.
    """
    from ..models import Comment, Like

    user = _target_user(user_id)
    articles_action = json_body().get("articles", "keep")
    if articles_action not in {"keep", "remove"}:
        raise ApiError(
            "Choose whether to keep or remove this account's articles.",
            status=422, field="articles",
        )

    if articles_action == "remove":
        Article.query.filter_by(
            contributor_id=user.id, status=ArticleStatus.PUBLISHED
        ).update({"status": ArticleStatus.UNPUBLISHED}, synchronize_session=False)

    Comment.query.filter_by(user_id=user.id).delete()
    Like.query.filter_by(user_id=user.id).delete()

    user.deleted_at = utcnow()
    user.is_suspended = True
    user.email = f"deleted-{user.id}@removed.invalid"
    user.password_hash = "!"
    user.bio = None

    _audit("user.delete", "user", user.id, f"articles={articles_action}")
    db.session.commit()
    return jsonify({"message": "Account removed.", "articles": articles_action})


@bp.post("/admin/users/<int:user_id>/role")
@admin_only
def set_role(user_id: int):
    """PDD Figure 5.56."""
    user = _target_user(user_id)
    raw = json_body().get("role")

    try:
        new_role = Role(raw)
    except ValueError:
        raise ApiError(f"Unknown role '{raw}'.", status=422, field="role")

    previous = user.role.value
    user.role = new_role
    _audit("user.role_change", "user", user.id, f"{previous} -> {new_role.value}")
    db.session.commit()
    return jsonify({"role": user.role.value})


def _target_user(user_id: int) -> User:
    user = User.query.filter_by(id=user_id, deleted_at=None).first()
    if user is None:
        raise ApiError("User not found.", status=404)
    if user.id == g.current_user.id:
        # An admin locking themselves out is an easy and unrecoverable mistake.
        raise ApiError("You cannot perform this action on your own account.", status=422)
    return user


# --------------------------------------------------------------------------- #
#  Contributor applications  (PDD Figures 5.54-5.55)
# --------------------------------------------------------------------------- #

@bp.get("/admin/applications")
@admin_only
def list_applications():
    applications = (
        ContributorApplication.query.filter_by(status=ApplicationStatus.PENDING)
        .order_by(ContributorApplication.created_at.asc())
        .all()
    )
    return jsonify(
        {
            "applications": [
                {
                    "id": a.id,
                    "userId": a.user_id,
                    "applicant": a.user.display_name,
                    "writingSample": a.writing_sample,
                    "background": a.background,
                    "submittedAt": a.created_at.isoformat(),
                }
                for a in applications
            ]
        }
    )


@bp.post("/admin/applications/<int:application_id>/decide")
@admin_only
def decide_application(application_id: int):
    """PDD Figure 5.55. Approval upgrades the account; rejection says when to reapply."""
    application = ContributorApplication.query.get(application_id)
    if application is None:
        raise ApiError("Application not found.", status=404)
    if application.status != ApplicationStatus.PENDING:
        raise ApiError("This application has already been decided.", status=409)

    data = json_body()
    decision = data.get("decision")
    reason = clean_plain_text(data.get("reason") or "")

    if decision not in {"approve", "reject"}:
        raise ApiError("Decision must be 'approve' or 'reject'.", status=422, field="decision")

    application.reviewed_by_id = g.current_user.id
    application.decision_reason = reason or None

    if decision == "approve":
        application.status = ApplicationStatus.APPROVED
        application.user.role = Role.VERIFIED_CONTRIBUTOR
        title, body = "You are now a Verified Contributor", "You can start writing."
    else:
        if not reason:
            raise ApiError("Tell the applicant why.", status=422, field="reason")
        application.status = ApplicationStatus.REJECTED
        # Bounded: an unchecked int() here crashes on "abc", and an unbounded one
        # lets a typo set a reapply date centuries out.
        cooldown_days = require_int(
            data, "reapplyAfterDays", default=30, minimum=1, maximum=365
        )
        application.reapply_after = utcnow() + timedelta(days=cooldown_days)
        title = "Your contributor application was not approved"
        body = f"{reason} You can reapply after {application.reapply_after.date().isoformat()}."

    db.session.add(
        Notification(
            user_id=application.user_id,
            event_type="application.decided",
            title=title,
            body=body,
        )
    )
    _audit(f"application.{decision}", "contributor_application", application.id, reason)
    db.session.commit()

    return jsonify({"status": application.status.value})


# --------------------------------------------------------------------------- #
#  Editor assignments
# --------------------------------------------------------------------------- #
#
#  PRD 1.3.2 says editors "work within a specific assigned content category", and
#  review.py enforces exactly that. Without these routes the assignment could
#  only be made by writing to the table directly, so a newly promoted editor had
#  a permanently empty review queue and no administrator could fix it.

@bp.get("/admin/editors")
@admin_only
def list_editor_assignments():
    editors = User.query.filter(
        User.role == Role.EDITOR, User.deleted_at.is_(None)
    ).order_by(User.display_name).all()

    assignments: dict[int, list] = {}
    rows = (
        db.session.query(EditorCategory, Category)
        .join(Category, Category.id == EditorCategory.category_id)
        .filter(EditorCategory.editor_id.in_([e.id for e in editors] or [-1]))
        .all()
    )
    for assignment, category in rows:
        assignments.setdefault(assignment.editor_id, []).append(
            {"id": category.id, "name": category.name}
        )

    return jsonify(
        {
            "editors": [
                {
                    "id": editor.id,
                    "name": editor.display_name,
                    "email": editor.email,
                    "categories": assignments.get(editor.id, []),
                    # Surfaced deliberately: this is the state that silently
                    # produces an empty review queue.
                    "hasNoCategories": not assignments.get(editor.id),
                }
                for editor in editors
            ]
        }
    )


@bp.put("/admin/editors/<int:editor_id>/categories")
@admin_only
def set_editor_categories(editor_id: int):
    """Replace an editor's category assignments outright.

    A PUT rather than incremental add/remove calls: the admin screen shows the
    full set of checkboxes, and sending the whole set avoids the lost-update
    problem two admins editing at once would otherwise hit.
    """
    editor = User.query.filter_by(id=editor_id, deleted_at=None).first()
    if editor is None:
        raise ApiError("User not found.", status=404)
    if editor.role != Role.EDITOR:
        raise ApiError(
            f"{editor.display_name} is not an editor. Change their role first.",
            status=422, field="editorId",
        )

    category_ids = require_id_list(json_body(), "categoryIds", max_items=50)

    found = Category.query.filter(
        Category.id.in_(category_ids or [-1]), Category.deleted_at.is_(None)
    ).all()
    if len(found) != len(set(category_ids)):
        raise ApiError(
            "One or more of those categories does not exist.",
            status=422, field="categoryIds",
        )

    EditorCategory.query.filter_by(editor_id=editor.id).delete()
    for category in found:
        db.session.add(EditorCategory(editor_id=editor.id, category_id=category.id))

    _audit(
        "editor.categories_set", "user", editor.id,
        ", ".join(c.name for c in found) or "none",
    )
    db.session.commit()

    return jsonify(
        {
            "editorId": editor.id,
            "categories": [{"id": c.id, "name": c.name} for c in found],
        }
    )


# --------------------------------------------------------------------------- #
#  Categories  (PDD Figure 5.59)
# --------------------------------------------------------------------------- #

@bp.post("/admin/categories")
@admin_only
def create_category():
    data = json_body()
    name = clean_plain_text(data.get("name") or "")
    if not name:
        raise ApiError("Give the category a name.", status=422, field="name")
    if Category.query.filter(func.lower(Category.name) == name.lower()).first():
        raise ApiError("A category with that name already exists.", status=409, field="name")

    category = Category(
        name=name,
        slug=slugify(name),
        description=clean_plain_text(data.get("description") or "") or None,
    )
    db.session.add(category)
    db.session.commit()
    return jsonify({"id": category.id, "name": category.name, "slug": category.slug}), 201


@bp.delete("/admin/categories/<int:category_id>")
@admin_only
def delete_category(category_id: int):
    """PDD Figure 5.59.

    The PDD leaves this open. Decision: soft-delete the category and reassign its
    articles to the "Uncategorised" system category. Cascading would destroy
    published work, which the platform's accountability model does not permit.
    """
    category = Category.query.filter_by(id=category_id, deleted_at=None).first()
    if category is None:
        raise ApiError("Category not found.", status=404)
    if category.is_system:
        raise ApiError("The fallback category cannot be deleted.", status=422)

    fallback = Category.query.filter_by(is_system=True).first()
    if fallback is None:
        raise ApiError(
            "No fallback category exists. Run the seed script first.", status=500
        )

    moved = Article.query.filter_by(category_id=category.id).update(
        {"category_id": fallback.id}
    )
    category.deleted_at = utcnow()

    _audit("category.delete", "category", category.id, f"{moved} articles reassigned")
    db.session.commit()
    return jsonify({"message": f"Category removed. {moved} articles reassigned."})


# --------------------------------------------------------------------------- #
#  Platform thresholds  (PDD Figure 5.60)
# --------------------------------------------------------------------------- #

@bp.get("/admin/settings")
@admin_only
def get_settings():
    """Effective values: shipped defaults with any admin override applied."""
    overrides = {row.key: row.value for row in PlatformSetting.query.all()}
    return jsonify(
        {
            "settings": [
                {
                    "key": key,
                    "value": overrides.get(key, default),
                    "default": default,
                    "isOverridden": key in overrides,
                }
                for key, default in DEFAULTS.items()
            ]
        }
    )


@bp.put("/admin/settings")
@admin_only
def update_settings():
    """Changing a threshold changes every published score, so rescore everything.

    This is O(articles) and is fine at project scale. At real scale it would be a
    background job, worth saying so in the report rather than pretending
    otherwise.
    """
    data = json_body().get("settings")
    if not isinstance(data, dict) or not data:
        raise ApiError(
            "Send a 'settings' object with at least one threshold.",
            status=422, field="settings",
        )

    # Validate every key before writing any, so a bad third value cannot leave
    # the first two applied.
    for key in data:
        if key not in DEFAULTS:
            raise ApiError(f"Unknown setting '{key}'.", status=422, field=key)

    for key in data:
        # require_number rejects NaN and infinity. Both survive a naive `< 0`
        # check (every comparison with NaN is False), and Postgres stores both
        # happily, which would drive every credibility score to nonsense with
        # no error anywhere.
        numeric = require_number(data, key, minimum=0, maximum=SETTING_CEILING)

        row = PlatformSetting.query.get(key)
        if row is None:
            row = PlatformSetting(key=key)
            db.session.add(row)
        row.value = numeric
        row.updated_by_id = g.current_user.id

    db.session.flush()

    contributors = User.query.filter(User.role.in_(list(
        {Role.VERIFIED_CONTRIBUTOR, Role.EDITOR, Role.SYSTEM_ADMIN}
    ))).all()
    for contributor in contributors:
        rescore_contributor_articles(contributor)

    _audit("settings.update", "platform_settings", 0, ", ".join(data))
    db.session.commit()
    return jsonify({"message": "Thresholds updated and all scores recalculated."})


# --------------------------------------------------------------------------- #
#  Dashboard and logs  (PDD Figures 5.61, 5.62)
# --------------------------------------------------------------------------- #

@bp.get("/admin/dashboard")
@admin_only
def dashboard():
    return jsonify(
        {
            "users": db.session.query(func.count(User.id)).filter(
                User.deleted_at.is_(None)
            ).scalar(),
            "published": db.session.query(func.count(Article.id)).filter(
                Article.status == ArticleStatus.PUBLISHED
            ).scalar(),
            "pendingReview": db.session.query(func.count(Article.id)).filter(
                Article.status == ArticleStatus.PENDING
            ).scalar(),
            "openReports": db.session.query(func.count(Report.id)).filter(
                Report.status == ReportStatus.OPEN
            ).scalar(),
            "averageCredibility": round(
                db.session.query(func.coalesce(func.avg(Article.credibility_score), 0))
                .filter(Article.status == ArticleStatus.PUBLISHED)
                .scalar()
                or 0,
                1,
            ),
        }
    )


@bp.get("/admin/logs")
@admin_only
def logs():
    action = request.args.get("action")
    query = AuditLog.query
    if action:
        query = query.filter(AuditLog.action == action)

    entries = query.order_by(AuditLog.created_at.desc()).limit(200).all()
    return jsonify(
        {
            "logs": [
                {
                    "id": e.id,
                    "actorId": e.actor_id,
                    "action": e.action,
                    "entityType": e.entity_type,
                    "entityId": e.entity_id,
                    "detail": e.detail,
                    "at": e.created_at.isoformat(),
                }
                for e in entries
            ]
        }
    )


# --------------------------------------------------------------------------- #
#  Article moderation  (PDD Figure 5.93)
# --------------------------------------------------------------------------- #

#: What an administrator may do to an article, keyed by its current status. The
#: interface renders only the relevant actions, and the server enforces the same
#: table rather than trusting it.
ARTICLE_ACTIONS = {
    ArticleStatus.PUBLISHED: {"suspend"},
    ArticleStatus.UNPUBLISHED: {"reinstate"},
    ArticleStatus.RETRACTED: {"reinstate"},
    ArticleStatus.PENDING: {"reject"},
    ArticleStatus.SCHEDULED: {"suspend"},
}


@bp.get("/admin/articles")
@admin_only
def list_all_articles():
    """Every article on the platform, not just one review queue.

    An editor sees their assigned sections; an administrator answers for the
    whole platform, which means being able to find any article regardless of who
    reviews that section.
    """
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status")

    query = Article.query
    if q:
        query = query.filter(Article.title.ilike(f"%{q}%"))
    if status:
        try:
            query = query.filter(Article.status == ArticleStatus(status))
        except ValueError:
            raise ApiError(f"Unknown status '{status}'.", status=422, field="status")

    articles = query.order_by(Article.updated_at.desc()).limit(100).all()
    return jsonify(
        {
            "articles": [
                {
                    "id": a.id,
                    "slug": a.slug,
                    "title": a.title,
                    "status": a.status.value,
                    "contributor": a.contributor.byline,
                    "credibilityScore": a.credibility_score,
                    "publishedAt": a.published_at.isoformat() if a.published_at else None,
                    "actions": sorted(ARTICLE_ACTIONS.get(a.status, set())),
                }
                for a in articles
            ]
        }
    )


@bp.post("/admin/articles/<int:article_id>/moderate")
@admin_only
def moderate_article(article_id: int):
    """Suspend, reinstate, or reject any article.

    Suspending unpublishes rather than deletes. A published article that was
    later corrected is the record of that correction, so the row survives even
    when the article comes off the site.
    """
    article = Article.query.get(article_id)
    if article is None:
        raise ApiError("Article not found.", status=404)

    action = json_body().get("action")
    allowed = ARTICLE_ACTIONS.get(article.status, set())
    if action not in allowed:
        raise ApiError(
            f"An article that is {article.status.value} cannot be {action or 'acted on'}."
            + (f" Available: {', '.join(sorted(allowed))}." if allowed else ""),
            status=409, field="action",
        )

    if action == "suspend":
        article.status = ArticleStatus.UNPUBLISHED
        title, body = "Your article was taken down", "An administrator suspended it."
    elif action == "reinstate":
        article.status = ArticleStatus.PUBLISHED
        title, body = "Your article is live again", "An administrator reinstated it."
    else:
        article.status = ArticleStatus.REJECTED
        title, body = "Your submission was rejected", "An administrator rejected it."

    db.session.add(
        Notification(
            user_id=article.contributor_id,
            event_type=f"article.{action}",
            title=title,
            body=body,
            link=f"/articles/{article.slug}",
        )
    )
    _audit(f"article.{action}", "article", article.id)
    db.session.commit()

    return jsonify({"status": article.status.value})
