"""Discovery and Search (PDD Section 2.2).

Covers PDD Figures 5.4 (trending), 5.5 (by category), 5.6 (article), 5.7 (search),
5.16 (personalised feed).

Search is rule-based keyword matching against title, tags, and category, exactly
as PDD Figure 5.7 states. There is deliberately no semantic or predictive
matching, because the ranking has to stay inspectable.
"""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError

from ..enums import ArticleStatus
from ..errors import ApiError
from ..extensions import db
from ..models import (
    Article, Category, Follow, Like, SavedArticle, User, UserCategoryPreference,
)
from ..countries import COUNTRIES, DEFAULT_COUNTRY, codes_matching
from ..credibility import DEFAULTS, credibility_score
from ..scoring_service import explain_article, load_settings
from ..source_rating import TIER_LABELS, TIER_POINTS, perennial

#: Plain descriptions of each source tier for the About page, in order.
SOURCE_TIER_DESCRIPTIONS = (
    ("official", "Government, parliament, courts, and bodies such as the UN and WHO."),
    ("research", "A published paper, identified by its DOI, that has not been retracted."),
    ("institution", "A university or research institute."),
    ("reliable", "An outlet Wikipedia's editors rate \u201cgenerally reliable\u201d after "
                 "public discussion."),
    ("unrated", "On no list, or rated \u201cno consensus\u201d. An editor can accept it."),
    ("unreliable", "Rated \u201cgenerally unreliable\u201d, or a platform where anyone "
                   "can publish, such as social media."),
    ("deprecated", "Deprecated or blacklisted by Wikipedia's editors. Flagged to the editor."),
    ("retracted", "A paper Crossref and Retraction Watch record as retracted. Flagged."),
    ("invalid", "A placeholder address, a page that does not exist, or a link cited twice."),
)
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


@bp.get("/countries")
def list_countries():
    """Every country with at least one published article, and how many.

    Countries with nothing published are left out: a page of 249 names, most
    leading to an empty list, would be a directory of absences.
    """
    rows = (
        db.session.query(Article.country_code, func.count())
        .filter(
            Article.status == ArticleStatus.PUBLISHED,
            Article.country_code.isnot(None),
        )
        .group_by(Article.country_code)
        .all()
    )
    countries = [
        {"code": code, "name": COUNTRIES[code], "articleCount": count}
        for code, count in rows
        if code in COUNTRIES
    ]
    countries.sort(key=lambda c: (-c["articleCount"], c["name"]))
    return jsonify({"countries": countries})


@bp.get("/countries/all")
def all_countries():
    """The full fixed list, for the article editor's country picker."""
    return jsonify(
        {
            "countries": sorted(
                ({"code": c, "name": n} for c, n in COUNTRIES.items()),
                key=lambda c: c["name"],
            ),
            "default": DEFAULT_COUNTRY,
        }
    )


@bp.get("/countries/<code>/articles")
def by_country(code: str):
    """One country's articles, optionally narrowed to a section.

    Country plus section ("Politics in Australia") is the unit the monthly
    digest compiles, so the filter exists here first.
    """
    code = code.upper()
    if code not in COUNTRIES:
        raise ApiError("Country not found.", status=404)

    page = request.args.get("page", 1, type=int)
    sort = request.args.get("sort", "recent")
    section = request.args.get("category")

    query = _published().filter(Article.country_code == code)

    # Sections that actually have articles for this country, for the filter
    # chips. Counted before the section filter is applied, so every chip stays
    # visible while one is selected.
    section_rows = (
        db.session.query(Category, func.count(Article.id))
        .join(Article, Article.category_id == Category.id)
        .filter(
            Article.status == ArticleStatus.PUBLISHED,
            Article.country_code == code,
            Category.deleted_at.is_(None),
        )
        .group_by(Category.id)
        .order_by(Category.name)
        .all()
    )

    selected = None
    if section:
        selected = Category.query.filter_by(slug=section, deleted_at=None).first()
        if selected is None:
            raise ApiError("Section not found.", status=404)
        query = query.filter(Article.category_id == selected.id)

    if sort == "credibility":
        query = query.order_by(Article.credibility_score.desc(), Article.published_at.desc())
    else:
        query = query.order_by(Article.published_at.desc(), Article.credibility_score.desc())

    result = _paginate(query, page)
    result["country"] = {"code": code, "name": COUNTRIES[code]}
    result["sections"] = [
        {"name": c.name, "slug": c.slug, "articleCount": n} for c, n in section_rows
    ]
    result["selectedSection"] = selected.slug if selected else None
    if not result["articles"] and page == 1:
        result["message"] = "No articles about this country yet"
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
                # "japan" finds articles tagged Japan even if the word is not
                # in the headline. Names are matched in Python against the
                # fixed list, then filtered by code.
                Article.country_code.in_(codes_matching(q) or ["--"]),
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
    # fails on a dropped pooled connection or a lock, the reader should still
    # get the article, so this failure is logged and swallowed rather than raised.
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

    # Whether this reader has already liked or saved it. Two small lookups on a
    # single article, deliberately not in serialize(): a list of twenty would
    # turn that into forty extra queries for something no list displays.
    payload["viewer"] = {"liked": False, "saved": False}
    if viewer is not None:
        payload["viewer"] = {
            "liked": db.session.query(
                Like.query.filter_by(article_id=article.id, user_id=viewer.id).exists()
            ).scalar(),
            "saved": db.session.query(
                SavedArticle.query.filter_by(
                    article_id=article.id, user_id=viewer.id
                ).exists()
            ).scalar(),
        }

    return jsonify({"article": payload})


@bp.get("/scoring/formula")
def scoring_formula():
    """What the credibility score is built from, in public.

    Team decision: the *inputs* are published, the *weights* are not. A reader
    can see that sourcing raises a score and a correction lowers it, and can
    read the per-article ledger showing what each input contributed to that
    particular article. The tuning constants themselves stay internal.

    So this returns no numbers. `min_articles_for_accuracy` is the one value a
    reader arguably needs, because "New contributor" is otherwise unexplained,
    and it is described in words rather than published as a figure.

    Public by design: the explanation is for readers, most of whom are not
    signed in.
    """
    return jsonify(
        {
            "inputs": [
                {
                    "name": "Contributor accuracy",
                    "effect": "raises",
                    "description": "The share of this writer's published articles "
                                   "that were never corrected or retracted. It is "
                                   "the largest single influence on a score.",
                },
                {
                    "name": "Sources",
                    "effect": "raises",
                    "description": "Each source raises the score by what kind of source "
                                   "it is, up to a fixed ceiling. Placeholders, social "
                                   "media and deprecated sites add nothing, so an "
                                   "article cannot be padded with links.",
                },
                {
                    "name": "Logged corrections",
                    "effect": "lowers",
                    "description": "Every correction an editor records lowers this "
                                   "article's score and the writer's accuracy rate.",
                },
                {
                    "name": "Retraction",
                    "effect": "lowers",
                    "description": "A withdrawn article carries the heaviest penalty "
                                   "of any single event.",
                },
                {
                    "name": "Upheld reader reports",
                    "effect": "lowers",
                    "description": "Once enough reader reports are upheld by an "
                                   "editor, the article is penalised and pulled into "
                                   "editorial review.",
                },
            ],
            # How each source is graded (app/source_rating.py). Served from the
            # rules themselves, so this page cannot drift from what they do.
            "sourceTiers": [
                {"tier": tier, "label": TIER_LABELS[tier], "points": TIER_POINTS[tier],
                 "description": description}
                for tier, description in SOURCE_TIER_DESCRIPTIONS
            ],
            "sourceLists": {
                "perennial": {
                    "name": "Wikipedia: Reliable sources/Perennial sources",
                    "url": perennial()["source"],
                    "license": perennial()["license"],
                    "retrieved": perennial()["retrieved"],
                },
                "retractions": {
                    "name": "Crossref, including the Retraction Watch database",
                    "url": "https://www.crossref.org/documentation/retrieve-metadata/retraction-watch/",
                },
            },
            "newContributor": (
                "A writer's accuracy rate is withheld until they have published a "
                "minimum number of articles. Until then their profile reads "
                "“New contributor”. That is a missing figure, not a low one, and "
                "it is never counted as zero."
            ),
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
