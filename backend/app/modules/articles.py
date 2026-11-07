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

import json
import re
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request
from sqlalchemy.orm import joinedload, selectinload

from ..enums import AUTHORING_ROLES, ArticleStatus, Role
from ..errors import ApiError
from ..extensions import db
from ..countries import country_name, normalise as normalise_country
from .images import find_attachable, image_urls
from ..originality_service import check as check_originality, index_article, summary as originality_summary
from ..source_service import rate_sources, serialize as serialize_source
from ..models import Article, ArticleRevision, ArticleSource, Category, utcnow
from ..sanitize import clean_article_body, clean_plain_text, preview_text
from ..review_service import category_problem
from ..translation_service import (
    fresh as fresh_translation, note as translation_note, pending as translation_pending, request_lang,
)
from ..scoring_service import load_settings, rescore_article
from ..security import current_user, roles_required
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


def _country(data: dict) -> str | None:
    """A submitted country code, validated against the fixed list. Null = international."""
    try:
        return normalise_country(data.get("countryCode"))
    except ValueError:
        raise ApiError("Choose a country from the list.", status=422, field="countryCode")


def _apply_cover(article: Article, data: dict) -> None:
    """Attach, replace or remove the cover image, and set its alt text and credit.

    `coverImage` is an image key from POST /images, or null to remove it. Only
    an image this writer uploaded can be attached.
    """
    if "coverImage" in data:
        key = data["coverImage"]
        if key is None or key == "":
            article.cover_image_id = None
        elif not isinstance(key, str):
            raise ApiError("'coverImage' must be an image key.", status=422, field="coverImage")
        else:
            article.cover_image_id = find_attachable(key, g.current_user).id
    if "coverImageAlt" in data:
        alt = require_str(data, "coverImageAlt", max_length=300, allow_empty=True, default=None)
        article.cover_image_alt = clean_plain_text(alt or "") or None
    if "coverImageCredit" in data:
        credit = require_str(
            data, "coverImageCredit", max_length=300, allow_empty=True, default=None
        )
        article.cover_image_credit = clean_plain_text(credit or "") or None


def _require_image_provenance(article: Article) -> None:
    """An image goes out with a description and a stated source, or not at all.

    Alt text is what a blind reader gets instead of the picture. The credit is
    the image's source, the same standard this platform holds claims to.
    """
    if article.cover_image_id is None:
        return
    if not article.cover_image_alt:
        raise ApiError("Describe the image for readers who cannot see it.",
                       status=422, field="coverImageAlt")
    if not article.cover_image_credit:
        raise ApiError("Say who took the image or where it came from.",
                       status=422, field="coverImageCredit")


def _cover(article: Article) -> dict | None:
    if article.cover_image is None:
        return None
    return {
        **image_urls(article.cover_image),
        "alt": article.cover_image_alt,
        "credit": article.cover_image_credit,
    }


def _reviewer(article: Article) -> dict | None:
    """Who vouched for this article, for the "Approved by" line.

    Only once it is public, and never while it is awaiting review: an
    auto-published article has had no editor vouch for it yet. `onPanel` says
    whether the name links to a public editor profile; an administrator can
    approve too but is not a member of the editor panel.
    """
    if article.status not in {ArticleStatus.PUBLISHED, ArticleStatus.RETRACTED}:
        return None
    if article.awaiting_review or article.reviewer is None:
        return None
    reviewer = article.reviewer
    return {
        "id": reviewer.id,
        "name": reviewer.byline,
        "title": reviewer.editor_title,
        "onPanel": reviewer.role == Role.EDITOR and reviewer.deleted_at is None,
    }


def list_loads() -> tuple:
    """Everything serialize() reads, fetched for a whole list in a few queries.

    Without these, each article on a page of twenty loads its writer, reviewer,
    cover image, sources and corrections one at a time: over fifty round trips
    to the database for one list. Image bytes stay deferred; only the row is read.
    """
    #All joined into the one article query. The database is a long way from
    #the API server, so each round trip costs far more than the few duplicate
    #rows the joined collections add (a page is twenty articles, each with a
    #handful of sources and rarely more than one correction).
    loads = (
        joinedload(Article.contributor),
        joinedload(Article.reviewer),
        joinedload(Article.cover_image),
        joinedload(Article.sources),
        joinedload(Article.corrections),
    )
    #In another language, the translations too: one more query for the list.
    if request_lang() != "en":
        loads += (selectinload(Article.translations),)
    return loads


def may_read(article: Article, viewer) -> bool:
    """Whether this viewer may read the article's full text."""
    return (
        not article.is_premium
        or (viewer is not None and (
            viewer.id == article.contributor_id
            or viewer.role in {Role.EDITOR, Role.SYSTEM_ADMIN}
            or viewer.has_premium_access()
        ))
    )


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
        "country": (
            {"code": article.country_code, "name": country_name(article.country_code)}
            if article.country_code else None
        ),
        "coverImageUrl": article.cover_image_url,
        "coverImage": _cover(article),
        #Republished under licence: who really wrote it and where it first
        #appeared. Readers are told on the page; the byline is not the author.
        "republication": json.loads(article.republication) if article.republication else None,
        "tags": [t for t in (article.tags or "").split(",") if t],
        "publishedAt": article.published_at.isoformat() if article.published_at else None,
        "submittedAt": article.submitted_at.isoformat() if article.submitted_at else None,
        #The writer has to be able to read why an editor sent it back.
        "rejectionReason": article.rejection_reason,
        "viewCount": article.view_count,
        "likeCount": article.like_count,
        "credibility": {
            "score": article.credibility_score,
            "band": article.credibility_band,
        },
        #Public, and deliberately separate from the score. The score is the
        #arithmetic; this says whether an editor has read the article yet. A
        #reader should never mistake one published by the system during a
        #backlog for one a human approved.
        "review": {
            "awaitingReview": article.awaiting_review,
            "autoPublishedAt": (
                article.auto_published_at.isoformat() if article.auto_published_at else None
            ),
            "reviewer": _reviewer(article),
        },
        "contributor": {
            "id": article.contributor_id,
            "name": article.contributor.byline,
            "accuracyRate": article.contributor.accuracy_rate,
        },
        #Each source carries its rating and the reason for it, so a reader
        #can see why one link counts for more than another.
        "sources": [serialize_source(s) for s in article.sources],
        #Public. A correction is why a score fell, and the product's claim is
        #that a reader can trace that. It is also how the writer finds the
        #correction they want to dispute.
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

    is_author = viewer is not None and viewer.id == article.contributor_id
    privileged = viewer is not None and viewer.role in {Role.EDITOR, Role.SYSTEM_ADMIN}
    if is_author or privileged:
        #An editorial tool, never shown to readers.
        payload["originality"] = originality_summary(article)

    #Another language: the translation's words, if there is a current one.
    lang = request_lang()
    translation = fresh_translation(article, lang) if lang != "en" else None
    if lang != "en":
        #None yet: where the site translates articles itself, one is on its way.
        preparing = translation is None and translation_pending(article, lang)
        payload["translation"] = translation_note(lang, translation, preparing)
        if translation is not None:
            payload["title"] = translation.title
            payload["summary"] = translation.summary
    body = translation.body if translation is not None else article.body

    if not include_body:
        return payload

    if may_read(article, viewer):
        payload["body"] = body
    else:
        #PDD Figure 5.6: a paywalled article shows a preview and a prompt.
        payload["bodyPreview"] = preview_text(body)
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
        country_code=_country(data),
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

    #Slug needs the id to guarantee uniqueness across identical titles.
    article.slug = slugify(title, article.id)
    _replace_sources(article, require_list(data, "sources", default=None, max_items=MAX_SOURCES))
    _apply_cover(article, data)
    index_article(article)

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

    #Each field is coerced before it reaches the sanitiser: bleach raises
    #TypeError on a non-string, which would surface as a 500 rather than a
    #message naming the offending field.
    if "title" in data:
        article.title = (
            clean_plain_text(require_str(data, "title", max_length=255)) or article.title
        )
    if "summary" in data:
        summary = require_str(data, "summary", max_length=500, allow_empty=True)
        article.summary = clean_plain_text(summary)[:500] or None
    if "body" in data:
        article.body = clean_article_body(require_str(data, "body", allow_empty=True))
        index_article(article)
        #The last report described different text.
        article.originality_percent = None
        article.originality_report = None
        article.originality_checked_at = None
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
    if "countryCode" in data:
        article.country_code = _country(data)
    _apply_cover(article, data)
    if article.status == ArticleStatus.PUBLISHED:
        #A live article never shows an image without its description and source.
        _require_image_provenance(article)
    if "sources" in data:
        _replace_sources(article, require_list(data, "sources", max_items=MAX_SOURCES))
        #Sources are a scoring input, so a live article's new sources are
        #rated at once and the score moves with them. A draft's are rated
        #when it is submitted.
        if article.status == ArticleStatus.PUBLISHED:
            db.session.flush()
            db.session.expire(article, ["sources"])
            rate_sources(article)
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
    problem = category_problem(article)
    if problem:
        raise ApiError(problem, status=422, field="categoryId")
    _require_image_provenance(article)

    #Every submission reaches the editor with its sources rated and its
    #originality report. Both inform the review; neither blocks submission.
    #Sources are rated first: the originality check compares only with the
    #sources that count.
    rate_sources(article)
    check_originality(article, settings=load_settings())

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
def revision_history(article_id: int):
    """Public once published, so a reader can trace a correction. Bodies are left
    out, so this cannot get around the paywall. Anything unpublished stays private."""
    article = Article.query.get(article_id)
    if article is None:
        raise ApiError("Article not found.", status=404)

    if article.status != ArticleStatus.PUBLISHED:
        viewer = current_user()
        if viewer is None:
            raise ApiError("Sign in to continue.", status=401)
        is_author = article.contributor_id == viewer.id
        if not is_author and viewer.role not in {Role.EDITOR, Role.SYSTEM_ADMIN}:
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
