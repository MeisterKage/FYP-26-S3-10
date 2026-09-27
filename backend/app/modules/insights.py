"""Writing signals for editors.

The article summary travels with the article itself (discovery.read_article);
this is the one insight with its own route, because only the editor reviewing
an article may see it. Writers do not: a list of what the check looks for is a
list of how to get past it, and a false flag shown to a writer reads as an
accusation.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from ..enums import REVIEW_ROLES
from ..errors import ApiError
from ..extensions import db
from ..insights_service import ProviderNotConfigured, writing_signals
from ..models import Article
from ..security import editor_owns_category, login_required

bp = Blueprint("insights", __name__)


@bp.get("/articles/<int:article_id>/writing-signals")
@login_required
def read_signals(article_id: int):
    article = db.session.get(Article, article_id)
    if (article is None or g.current_user.role not in REVIEW_ROLES
            or not editor_owns_category(article.category_id)):
        raise ApiError("Article not found.", status=404)
    try:
        return jsonify({"signals": writing_signals(article)})
    except ProviderNotConfigured as exc:
        raise ApiError(str(exc), status=503) from exc
