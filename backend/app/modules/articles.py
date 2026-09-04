"""Article Management (PDD Section 2.2).

Drafting, submission, scheduling, publishing, and revision history.
Covers PDD Figures 5.41-5.46.

Lifecycle:

    DRAFT --submit--> PENDING --approve--> PUBLISHED
                         |                     |
                         |                     +--schedule--> SCHEDULED --> PUBLISHED
                         +--reject---> REJECTED
    PUBLISHED --unpublish--> UNPUBLISHED
    PUBLISHED --retract----> RETRACTED

Approval lives in `review.py` because it is an editor action, not an author one.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

from ..enums import AUTHORING_ROLES, ArticleStatus, Role
from ..errors import ApiError
from ..extensions import db
from ..models import Article, ArticleRevision, ArticleSource, Category, utcnow
from ..sanitize import clean_article_body, clean_plain_text, preview_text
from ..scoring_service import rescore_article
from ..security import login_required, roles_required
from ..validation import json_body, require_int, require_list, require_str

bp = Blueprint("articles", __name__)

#: Statuses an author may still edit freely.
EDITABLE = {ArticleStatus.DRAFT, ArticleStatus.REJECTED}

#: Caps on repeated fields. Without them a client can push a column past its
#: declared length and turn a validation problem into a database error.
MAX_TAGS = 10
MAX_SOURCES = 20


def slugify(title: str, article_id: int | None = None) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:200] or "article"
    return f"{base}-{article_id}" if article_id else base


def _clean_tags(data: dict) -> str | None:
    """Normalise the tags list.

    require_list rejects a bare string. Iterating one would not raise; it would
    quietly produce a tag per character ("news" becomes n,e,w,s), which is the
    kind of bug that survives to the demo because nothing ever errors.
    """
    raw = require_list(data, "tags", default=None, max_items=MAX_TAGS)

    tags = []
    for entry in raw:
        if not isinstance(entry, str):
            raise ApiError("Tags must be text.", status=422, field="tags")
        cleaned = clean_plain_text(entry)[:40]
        if cleaned and "," not in cleaned and cleaned not in tags:
            tags.append(cleaned)

    return ",".join(tags)[:500] or None


def serialize(article: Article, *, include_body: bool = True, viewer=None) -> dict:
    """Serialise an article.

    The premium paywall is enforced HERE, by omitting the body from the payload.
    Never send a premium body and hide it in the client; the response is
    trivially readable in devtools.
    """
    payload = {
        "id": article.id,
        "slug": article.slug,
        "title": article.title,
        "summary": article.summary,
        "status": article.status.value,
        "isPremium": article.is_premium,
        "categoryId": article.category_id,
        "coverImageUrl": article.cover_image_url,
        "tags": [t for t in (article.tags or "").split(",") if t],
        "publishedAt": article.published_at.isoformat() if article.published_at else None,
        "submittedAt": article.submitted_at.isoformat() if article.submitted_at else None,
        # The writer has to be able to read why an editor sent it back.
        "rejectionReason": article.rejection_reason,
        "viewCount": article.view_count,
        "likeCount": article.like_count,
        "credibility": {
            "score": article.credibility_score,
            "band": article.credibility_band,
        },
        "contributor": {
            "id": article.contributor_id,
            "name": article.contributor.byline,
            "accuracyRate": article.contributor.accuracy_rate,
        },
        "sources": [
            {"url": s.url, "label": s.label, "isValid": s.is_valid} for s in article.sources
        ],
        # Public. A correction is why a score fell, and the product's claim is
        # that a reader can trace that. It is also how the writer finds the
        # correction they want to dispute.
        "corrections": [
            {
                "id": c.id,
                "type": c.correction_type.value,
                "reason": c.reason,
                "issuedAt": c.created_at.isoformat(),
                "overturned": c.overturned_at is not None,
            }
            for c in sorted(article.corrections, key=lambda c: c.created_at, reverse=True)
        ],
    }

    if not include_body:
        return payload

    is_author = viewer is not None and viewer.id == article.contributor_id
    privileged = viewer is not None and viewer.role in {Role.EDITOR, Role.SYSTEM_ADMIN}
    may_read_premium = (
        not article.is_premium
        or is_author
        or privileged
        or (viewer is not None and viewer.has_premium_access())
    )

    if may_read_premium:
        payload["body"] = article.body
    else:
        # PDD Figure 5.6: a paywalled article shows a preview and a prompt.
        payload["bodyPreview"] = preview_text(article.body)
        payload["paywalled"] = True

    return payload


def _owned_article(article_id: int) -> Article:
    article = Article.query.get(article_id)
    if article is None:
        raise ApiError("Article not found.", status=404)
    if article.contributor_id != g.current_user.id:
        raise ApiError("You can only manage your own articles.", status=403)
    return article


@bp.post("/articles")
@roles_required(*AUTHORING_ROLES)
def create_article():
    """PDD Figure 5.41."""
    data = json_body()

    title = clean_plain_text(data.get("title") or "")
    if not title:
        raise ApiError("Give the article a title.", status=422, field="title")

    category_id = require_int(data, "categoryId", minimum=1)
    category = Category.query.filter_by(id=category_id, deleted_at=None).first()
    if category is None:
        raise ApiError("Choose a category.", status=422, field="categoryId")

    article = Article(
        contributor_id=g.current_user.id,
        category_id=category.id,
        title=title,
        slug=slugify(title),
        summary=clean_plain_text(data.get("summary") or "")[:500] or None,
        body=clean_article_body(data.get("body") or ""),
        tags=_clean_tags(data),
        is_premium=bool(data.get("isPremium")),
        status=ArticleStatus.DRAFT,
    )
    db.session.add(article)
    db.session.flush()

    # Slug needs the id to guarantee uniqueness across identical titles.
    article.slug = slugify(title, article.id)
    _replace_sources(article, require_list(data, "sources", default=None, max_items=MAX_SOURCES))

    db.session.commit()
    return jsonify(serialize(article, viewer=g.current_user)), 201


@bp.patch("/articles/<int:article_id>")
@roles_required(*AUTHORING_ROLES)
def update_article(article_id: int):
    """PDD Figure 5.42. Editing a published article writes a revision first."""
    article = _owned_article(article_id)
    data = json_body()

    if article.status not in EDITABLE and article.status != ArticleStatus.PUBLISHED:
        raise ApiError(
            f"An article that is {article.status.value} cannot be edited.", status=409
        )

    if article.status == ArticleStatus.PUBLISHED:
        db.session.add(
            ArticleRevision(
                article_id=article.id,
                editor_id=g.current_user.id,
                title=article.title,
                body=article.body,
                change_note=require_str(
                    data, "changeNote", default=None, max_length=1000, allow_empty=True
                ) or None,
            )
        )

    # Each field is coerced before it reaches the sanitiser: bleach raises
    # TypeError on a non-string, which would surface as a 500 rather than a
    # message naming the offending field.
    if "title" in data:
        article.title = (
            clean_plain_text(require_str(data, "title", max_length=255)) or article.title
        )
    if "summary" in data:
        summary = require_str(data, "summary", max_length=500, allow_empty=True)
        article.summary = clean_plain_text(summary)[:500] or None
    if "body" in data:
        article.body = clean_article_body(require_str(data, "body", allow_empty=True))
    if "isPremium" in data:
        article.is_premium = bool(data["isPremium"])
    if "tags" in data:
        article.tags = _clean_tags(data)
    if "categoryId" in data:
        category_id = require_int(data, "categoryId", minimum=1)
        category = Category.query.filter_by(id=category_id, deleted_at=None).first()
        if category is None:
            raise ApiError("That category does not exist.", status=422, field="categoryId")
        article.category_id = category.id
    if "sources" in data:
        _replace_sources(article, require_list(data, "sources", max_items=MAX_SOURCES))
        # Source count is a scoring input, so the score moves with it.
        if article.status == ArticleStatus.PUBLISHED:
            rescore_article(article)

    db.session.commit()
    return jsonify(serialize(article, viewer=g.current_user))


@bp.post("/articles/<int:article_id>/submit")
@roles_required(*AUTHORING_ROLES)
def submit_article(article_id: int):
    """PDD Figure 5.45. Sends the article to the assigned category editor."""
    article = _owned_article(article_id)

    if article.status not in EDITABLE:
        raise ApiError(
            f"This article is already {article.status.value}.", status=409
        )
    if not article.body.strip():
        raise ApiError("Add some content before submitting.", status=422, field="body")

    article.status = ArticleStatus.PENDING
    article.submitted_at = utcnow()
    article.rejection_reason = None

    db.session.commit()
    return jsonify(serialize(article, viewer=g.current_user))


@bp.post("/articles/<int:article_id>/schedule")
@roles_required(*AUTHORING_ROLES)
def schedule_article(article_id: int):
    """PDD Figure 5.44. Only an already-approved article may be scheduled."""
    article = _owned_article(article_id)
    data = json_body()

    if article.status not in {ArticleStatus.PUBLISHED, ArticleStatus.SCHEDULED}:
        raise ApiError("Only an approved article can be scheduled.", status=409)

    raw = data.get("publishAt")
    if not raw:
        raise ApiError("Choose a publication time.", status=422, field="publishAt")

    try:
        when = datetime.fromisoformat(raw)
    except ValueError:
        raise ApiError("That date could not be read.", status=422, field="publishAt")

    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    if when <= datetime.now(timezone.utc):
        raise ApiError("Choose a time in the future.", status=422, field="publishAt")

    article.status = ArticleStatus.SCHEDULED
    article.published_at = when

    db.session.commit()
    return jsonify(serialize(article, viewer=g.current_user))


@bp.delete("/articles/<int:article_id>")
@roles_required(*AUTHORING_ROLES)
def unpublish_or_delete(article_id: int):
    """PDD Figure 5.43.

    A draft is deleted outright. A published article is unpublished, never
    destroyed; its revision and correction history is part of the platform's
    accountability record.
    """
    article = _owned_article(article_id)

    if article.status in EDITABLE:
        db.session.delete(article)
        db.session.commit()
        return jsonify({"message": "Draft deleted."})

    article.status = ArticleStatus.UNPUBLISHED
    db.session.commit()
    return jsonify({"message": "Article unpublished.", "article": serialize(article,
                                                                           viewer=g.current_user)})


@bp.get("/articles/<int:article_id>")
@roles_required(*AUTHORING_ROLES)
def read_own_article(article_id: int):
    """The article behind the editing screen (PDD Figure 5.42).

    The public route is keyed on slug and withholds a premium body. This one is
    keyed on id, is owner-scoped, and always includes the body, because a writer
    editing their own draft is the one reader who must always see all of it.
    """
    article = _owned_article(article_id)
    return jsonify({"article": serialize(article, viewer=g.current_user)})


@bp.get("/articles/mine")
@roles_required(*AUTHORING_ROLES)
def my_articles():
    """The contributor dashboard list, with Draft / Pending / Published status."""
    status = request.args.get("status")
    query = Article.query.filter_by(contributor_id=g.current_user.id)

    if status:
        try:
            query = query.filter_by(status=ArticleStatus(status))
        except ValueError:
            raise ApiError(f"Unknown status '{status}'.", status=422, field="status")

    articles = query.order_by(Article.updated_at.desc()).all()
    return jsonify(
        {"articles": [serialize(a, include_body=False, viewer=g.current_user) for a in articles]}
    )


@bp.get("/articles/<int:article_id>/revisions")
@login_required
def revision_history(article_id: int):
    article = Article.query.get(article_id)
    if article is None:
        raise ApiError("Article not found.", status=404)

    is_author = article.contributor_id == g.current_user.id
    if not is_author and g.current_user.role not in {Role.EDITOR, Role.SYSTEM_ADMIN}:
        raise ApiError("You cannot view this article's history.", status=403)

    revisions = (
        ArticleRevision.query.filter_by(article_id=article.id)
        .order_by(ArticleRevision.created_at.desc())
        .all()
    )
    return jsonify(
        {
            "revisions": [
                {
                    "id": r.id,
                    "title": r.title,
                    "changeNote": r.change_note,
                    "createdAt": r.created_at.isoformat(),
                }
                for r in revisions
            ]
        }
    )


def _replace_sources(article: Article, sources: list) -> None:
    """Rewrite the article's source links.

    Source count feeds the Credibility Score, so this deliberately validates
    shape before persisting; a malformed URL must not silently earn points.
    """
    ArticleSource.query.filter_by(article_id=article.id).delete()

    for entry in sources[:MAX_SOURCES]:
        url = (entry.get("url") if isinstance(entry, dict) else entry) or ""
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            continue
        db.session.add(
            ArticleSource(
                article_id=article.id,
                url=url[:1000],
                label=clean_plain_text((entry.get("label") if isinstance(entry, dict) else "") or "")[:255]
                or None,
                is_valid=True,
            )
        )
