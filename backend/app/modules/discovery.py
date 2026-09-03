"""Discovery and Search (PDD Section 2.2).

Covers PDD Figures 5.4 (trending), 5.5 (by category), 5.6 (article), 5.7 (search),
5.16 (personalised feed).

Search is rule-based keyword matching against title, tags, and category, exactly
as PDD Figure 5.7 states. There is deliberately no semantic or predictive
matching -- the platform's whole pitch is that its ranking is inspectable.
"""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from ..enums import ArticleStatus
from ..errors import ApiError
from ..extensions import db
from ..models import (
    Article, Category, Follow, User, UserCategoryPreference,
)
from ..credibility import DEFAULTS, credibility_score
from ..scoring_service import explain_article, load_settings
from ..security import current_user
from .articles import serialize

bp = Blueprint("discovery", __name__)

PAGE_SIZE = 20


def _published():
    return Article.query.filter(Article.status == ArticleStatus.PUBLISHED)


def _paginate(query, page: int):
    items = query.limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()
    return {
        "articles": [serialize(a, include_body=False, viewer=current_user()) for a in items],
        "page": page,
        "hasMore": len(items) == PAGE_SIZE,
    }


@bp.get("/categories")
def list_categories():
    categories = Category.query.filter_by(deleted_at=None).order_by(Category.name).all()
    return jsonify(
        {
            "categories": [
                {"id": c.id, "name": c.name, "slug": c.slug, "description": c.description}
                for c in categories
            ]
        }
    )


@bp.get("/feed/trending")
def trending():
    """PDD Figure 5.4: top articles ranked by recency and credibility score."""
    page = request.args.get("page", 1, type=int)
    query = _published().order_by(
        Article.published_at.desc(), Article.credibility_score.desc()
    )
    return jsonify(_paginate(query, page))


@bp.get("/feed/personalised")
def personalised():
    """PDD Figure 5.16.

    Two rows: articles matching stated interests, and articles from followed
    contributors. A signed-out or preference-less user gets trending instead of an
    empty page, which the figure requires explicitly.
    """
    user = current_user()
    if user is None:
        return trending()

    interest_ids = [
        p.category_id for p in UserCategoryPreference.query.filter_by(user_id=user.id)
    ]
    followed_ids = [
        f.contributor_id for f in Follow.query.filter_by(follower_id=user.id)
    ]

    if not interest_ids and not followed_ids:
        return trending()

    by_interest = (
        _published()
        .filter(Article.category_id.in_(interest_ids or [-1]))
        .order_by(Article.published_at.desc())
        .limit(PAGE_SIZE)
        .all()
    )
    from_followed = (
        _published()
        .filter(Article.contributor_id.in_(followed_ids or [-1]))
        .order_by(Article.published_at.desc())
        .limit(PAGE_SIZE)
        .all()
    )

    return jsonify(
        {
            "forYou": [serialize(a, include_body=False, viewer=user) for a in by_interest],
            "fromFollowed": [serialize(a, include_body=False, viewer=user) for a in from_followed],
        }
    )


@bp.get("/categories/<slug>/articles")
def by_category(slug: str):
    """PDD Figure 5.5."""
    category = Category.query.filter_by(slug=slug, deleted_at=None).first()
    if category is None:
        raise ApiError("Category not found.", status=404)

    page = request.args.get("page", 1, type=int)
    sort = request.args.get("sort", "recent")

    query = _published().filter(Article.category_id == category.id)
    if sort == "credibility":
        query = query.order_by(Article.credibility_score.desc(), Article.published_at.desc())
    else:
        query = query.order_by(Article.published_at.desc(), Article.credibility_score.desc())

    result = _paginate(query, page)
    result["category"] = {"id": category.id, "name": category.name, "slug": category.slug}
    if not result["articles"] and page == 1:
        result["message"] = "No articles available in this category"
    return jsonify(result)


@bp.get("/search")
def search():
    """PDD Figure 5.7. Keyword matching against title, tags, and category."""
    q = (request.args.get("q") or "").strip()
    page = request.args.get("page", 1, type=int)

    if not q:
        raise ApiError("Enter something to search for.", status=422, field="q")

    like = f"%{q}%"
    query = (
        _published()
        .join(Category, Category.id == Article.category_id)
        .filter(
            or_(
                Article.title.ilike(like),
                Article.tags.ilike(like),
                Article.summary.ilike(like),
                Category.name.ilike(like),
            )
        )
        .order_by(Article.credibility_score.desc(), Article.published_at.desc())
    )

    result = _paginate(query, page)
    result["query"] = q
    if not result["articles"] and page == 1:
        result["message"] = "No results found"
    return jsonify(result)


@bp.get("/articles/<slug>")
def read_article(slug: str):
    """PDD Figure 5.6. Byline, publish time, credibility score, accuracy rate, body."""
    article = Article.query.filter_by(slug=slug).first()
    if article is None:
        raise ApiError("Article not found.", status=404)

    viewer = current_user()
    is_author = viewer is not None and viewer.id == article.contributor_id
    if article.status != ArticleStatus.PUBLISHED and not is_author:
        raise ApiError("Article not found.", status=404)

    # A view counter is the least important thing on this page. If the write
    # fails -- a dropped pooled connection, a lock -- the reader should still get
    # the article, so this failure is logged and swallowed rather than raised.
    try:
        article.view_count += 1
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning("Could not record a view for article %s", article.id)

    payload = serialize(article, viewer=viewer)

    # PRD 1.3.3 promises a reader can trace exactly why a score is what it is.
    # The breakdown travels with the article so the promise is kept on the page
    # rather than in a document nobody opens.
    if article.status in {ArticleStatus.PUBLISHED, ArticleStatus.RETRACTED}:
        payload["credibility"] = {
            **payload["credibility"],
            **explain_article(article).as_dict(),
        }

    return jsonify({"article": payload})


@bp.get("/scoring/formula")
def scoring_formula():
    """The disclosed formula, in public.

    Administrators can change every constant at runtime (PRD 1.3.2), so the
    About page reads them from here rather than hard-coding numbers that would
    silently go stale the first time a threshold moved.

    Public by design: a formula behind authentication is not disclosed.
    """
    cfg = {**DEFAULTS, **load_settings()}

    # A worked example, computed by the real engine rather than written by hand,
    # so the page can never print arithmetic the platform would not produce.
    example = credibility_score(
        contributor_accuracy=92.0,
        source_count=3,
        correction_count=0,
        is_retracted=False,
        upheld_report_count=0,
        settings=cfg,
    )

    return jsonify(
        {
            "constants": {
                **{k: cfg[k] for k in DEFAULTS},
                "example": {
                    "accuracy": 92,
                    "sources": 3,
                    "accuracy_component": example.accuracy_component,
                    "source_component": example.source_component,
                    "score": example.score,
                    "band": example.band,
                },
            },
            "bands": [
                {
                    "label": label,
                    "sample": sample,
                    "description": description,
                }
                for label, sample, description in (
                    ("High", 88, "A well-sourced article from a writer with few or "
                                 "no corrections against their published work."),
                    ("Moderate", 68, "Sound, but either lightly sourced or written by "
                                     "someone with corrections in their record."),
                    ("Low", 48, "Thin sourcing, a correction on this article, or both. "
                                "Worth reading with the sources open."),
                    ("Disputed", 28, "Retracted, or enough reader reports were upheld "
                                     "to trigger editorial review. Shown hatched."),
                )
            ],
        }
    )


@bp.get("/contributors/<int:user_id>")
def contributor_profile(user_id: int):
    """A contributor's public profile: accuracy rate, or 'New Contributor'."""
    user = User.query.filter_by(id=user_id, deleted_at=None).first()
    if user is None:
        raise ApiError("Contributor not found.", status=404)

    articles = (
        _published()
        .filter(Article.contributor_id == user.id)
        .order_by(Article.published_at.desc())
        .limit(PAGE_SIZE)
        .all()
    )

    return jsonify(
        {
            "contributor": {
                "id": user.id,
                "name": user.byline,
                "bio": user.bio,
                # NULL accuracy is "New Contributor", not zero (PRD 1.3.3).
                "accuracyRate": user.accuracy_rate,
                "isNewContributor": user.accuracy_rate is None,
                "followerCount": db.session.query(Follow)
                .filter_by(contributor_id=user.id)
                .count(),
            },
            "articles": [
                serialize(a, include_body=False, viewer=current_user()) for a in articles
            ],
        }
    )
