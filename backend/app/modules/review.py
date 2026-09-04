"""Editorial review (PDD Figures 5.48-5.49).

An editor sees only the queue for the categories they are assigned to
(PRD 1.3.2: editors "work within a specific assigned content category").
Administrators see everything, which PRD 1.3.2 grants them explicitly.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..enums import REVIEW_ROLES, ArticleStatus, Role
from ..errors import ApiError
from ..extensions import db
from ..models import Article, AuditLog, EditorCategory, Notification, utcnow
from ..sanitize import clean_plain_text
from ..scoring_service import explain_article, rescore_article
from ..security import editor_owns_category, roles_required
from ..validation import json_body, require_choice, require_str
from .articles import serialize

bp = Blueprint("review", __name__)


def _assigned_category_ids() -> list[int] | None:
    """None means 'every category' (administrators)."""
    if g.current_user.role == Role.SYSTEM_ADMIN:
        return None
    return [
        row.category_id
        for row in EditorCategory.query.filter_by(editor_id=g.current_user.id)
    ]


@bp.get("/review/queue")
@roles_required(*REVIEW_ROLES)
def review_queue():
    """PDD Figure 5.48. Oldest submission first, a queue, not a feed."""
    query = Article.query.filter_by(status=ArticleStatus.PENDING)

    category_ids = _assigned_category_ids()
    if category_ids is not None:
        if not category_ids:
            # An editor with no assigned category has an empty queue, not an error.
            return jsonify({"articles": [], "note": "No categories are assigned to you yet."})
        query = query.filter(Article.category_id.in_(category_ids))

    articles = query.order_by(Article.submitted_at.asc()).all()

    # A pending article has never been scored, so its stored credibility_score is
    # still the 0.0 default. Serving that reads to an editor as "this article is
    # worthless" rather than "not yet scored". That is the opposite of true, on
    # the one screen where it would bias the decision. Compute the score the article
    # *would* carry on publication instead. Read-only: explain_article persists
    # nothing.
    payload = []
    for article in articles:
        data = serialize(article, viewer=g.current_user)
        data["credibility"] = {
            **data["credibility"],
            **explain_article(article).as_dict(),
            "prospective": True,
        }
        payload.append(data)

    return jsonify({"articles": payload})


@bp.post("/review/<int:article_id>/approve")
@roles_required(*REVIEW_ROLES)
def approve(article_id: int):
    """PDD Figure 5.49.

    Publishing is the moment the score first matters: PRD 1.3.3 requires the
    credibility score to be visible from the instant the article goes live, so it
    is computed here rather than lazily on first read.
    """
    article = _pending_article(article_id)

    article.status = ArticleStatus.PUBLISHED
    article.published_at = utcnow()
    article.reviewed_by_id = g.current_user.id
    article.rejection_reason = None

    breakdown = rescore_article(article)

    db.session.add(
        Notification(
            user_id=article.contributor_id,
            event_type="article.approved",
            title="Your article has been published",
            body=f"'{article.title}' is now live.",
            link=f"/articles/{article.slug}",
        )
    )
    db.session.add(
        AuditLog(
            actor_id=g.current_user.id,
            action="article.approve",
            entity_type="article",
            entity_id=article.id,
        )
    )
    db.session.commit()

    return jsonify(
        {"article": serialize(article, viewer=g.current_user), "credibility": breakdown.as_dict()}
    )


@bp.post("/review/<int:article_id>/reject")
@roles_required(*REVIEW_ROLES)
def reject(article_id: int):
    """PDD Figure 5.49. A rejected article returns to the author, editable."""
    article = _pending_article(article_id)
    data = json_body()

    reason = clean_plain_text(data.get("reason") or "")
    if not reason:
        raise ApiError(
            "Give the contributor a reason for the rejection.", status=422, field="reason"
        )

    article.status = ArticleStatus.REJECTED
    article.reviewed_by_id = g.current_user.id
    article.rejection_reason = reason

    db.session.add(
        Notification(
            user_id=article.contributor_id,
            event_type="article.rejected",
            title="Your article needs changes",
            body=reason,
            link=f"/dashboard/articles/{article.id}",
        )
    )
    db.session.add(
        AuditLog(
            actor_id=g.current_user.id,
            action="article.reject",
            entity_type="article",
            entity_id=article.id,
            detail=reason,
        )
    )
    db.session.commit()

    return jsonify({"article": serialize(article, viewer=g.current_user)})


def _pending_article(article_id: int) -> Article:
    article = Article.query.get(article_id)
    if article is None:
        raise ApiError("Article not found.", status=404)
    if article.status != ArticleStatus.PENDING:
        raise ApiError(
            f"This article is {article.status.value}, not awaiting review.", status=409
        )
    if not editor_owns_category(article.category_id):
        raise ApiError("This article is outside your assigned categories.", status=403)

    # Separation of duties. Editors may write (AUTHORING_ROLES includes them),
    # and without this an editor could write, submit, and approve their own
    # article inside their own section, skipping the only human check between a
    # claim and a published credibility score. PRD 7.4.2 commits to review
    # before publication, which a review by the author is not.
    #
    # Administrators are exempt: PRD 1.3.2 grants them oversight of everything,
    # and an administrator publishing their own piece is a deliberate act by the
    # one role that can already override any editorial decision.
    if (
        article.contributor_id == g.current_user.id
        and g.current_user.role != Role.SYSTEM_ADMIN
    ):
        raise ApiError(
            "You wrote this article, so another editor or an administrator has to "
            "review it.",
            status=403,
        )

    return article
