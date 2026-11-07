"""Originality reports: run a check, and read the latest one.

A writer checks their own article before submitting; an editor reads the
report on anything in their sections. Submission runs the check itself, so an
editor never sees a submission without one.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from ..enums import AUTHORING_ROLES, REVIEW_ROLES, Role
from ..errors import ApiError
from ..extensions import db
from ..models import Article
from ..originality_service import check, for_viewer, stored_report
from ..ratelimit import client_address, limiter
from ..security import editor_owns_category, login_required
from ..scoring_service import load_settings

bp = Blueprint("originality", __name__)

#: Each check can fetch up to ten cited pages, so it is not free to run.
CHECK_LIMIT = "20 per hour"


def _checker() -> str:
    user = g.get("current_user")
    return f"user:{user.id}" if user else client_address()


def _article_for(article_id: int) -> Article:
    """The article, if this user wrote it or reviews its section. 404 otherwise."""
    article = db.session.get(Article, article_id)
    user = g.current_user
    allowed = article is not None and (
        (article.contributor_id == user.id and user.role in AUTHORING_ROLES)
        or (user.role in REVIEW_ROLES and editor_owns_category(article.category_id))
    )
    if not allowed:
        #404 rather than 403: whether an article exists is itself private
        #while it is a draft.
        raise ApiError("Article not found.", status=404)
    return article


@bp.post("/articles/<int:article_id>/originality")
@limiter.limit(CHECK_LIMIT, key_func=_checker)
@login_required
def run_check(article_id: int):
    article = _article_for(article_id)
    if not (article.body or "").strip():
        raise ApiError("Add some text before checking it.", status=422, field="body")
    report = check(article, settings=load_settings())
    db.session.commit()
    return jsonify({"report": for_viewer(report, article, g.current_user)})


@bp.get("/articles/<int:article_id>/originality")
@login_required
def read_report(article_id: int):
    article = _article_for(article_id)
    return jsonify({"report": for_viewer(stored_report(article), article, g.current_user)})
