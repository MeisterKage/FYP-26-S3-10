"""Tone and trend analysis for one article (GET /articles/<slug>/analysis).

Public for published articles, like the score: a reader can see how an
article's language reads and how attention to it is moving. Loaded when the
reader opens the panel, so the article itself stays quick.
"""
from __future__ import annotations

from datetime import timedelta
from statistics import mean

from flask import Blueprint, jsonify
from sqlalchemy import func

from .. import analysis
from ..enums import ArticleStatus
from ..errors import ApiError
from ..extensions import db
from ..models import Article, ArticleDailyView, Category, Comment, Like, utcnow
from ..security import current_user

bp = Blueprint("analysis", __name__)

DAYS = 14
WEEKS = 8


def _by_day(rows) -> dict:
    out: dict = {}
    for when, count in rows:
        day = when if not hasattr(when, "date") else when.date()
        out[day] = out.get(day, 0) + count
    return out


@bp.get("/articles/<slug>/analysis")
def article_analysis(slug: str):
    article = Article.query.filter_by(slug=slug).first()
    viewer = current_user()
    if article is None or (article.status != ArticleStatus.PUBLISHED
                           and not (viewer and viewer.id == article.contributor_id)):
        raise ApiError("Article not found.", status=404)

    today = utcnow().date()
    since = today - timedelta(days=DAYS - 1)

    # Paywalled text is not analysed for readers who cannot open it: the tone
    # strip would describe paragraphs they have not been shown.
    from .articles import may_read
    readable = may_read(article, viewer)
    tone = analysis.tone(article.body) if readable else None

    views = _by_day(
        db.session.query(ArticleDailyView.day, ArticleDailyView.views)
        .filter(ArticleDailyView.article_id == article.id, ArticleDailyView.day >= since)
    )
    likes = _by_day(
        db.session.query(Like.created_at, func.count()).filter(
            Like.article_id == article.id, Like.created_at >= since).group_by(Like.created_at)
    )
    comments = _by_day(
        db.session.query(Comment.created_at, func.count()).filter(
            Comment.article_id == article.id, Comment.created_at >= since).group_by(Comment.created_at)
    )
    view_series = analysis.daily_series(views, today, DAYS)

    # The topic around it: how much the section has published each week, and
    # how this article's tone compares with the section's recent articles.
    category = db.session.get(Category, article.category_id)
    window = today - timedelta(days=7 * WEEKS - 1)
    peers = (
        db.session.query(Article.id, Article.published_at, Article.body)
        .filter(Article.status == ArticleStatus.PUBLISHED,
                Article.category_id == article.category_id,
                Article.published_at >= window)
        .all()
    )
    peer_tones = [analysis.tone(p.body)["score"] for p in peers if p.id != article.id]
    topic_tone = round(mean(peer_tones), 3) if peer_tones else None

    return jsonify({
        "tone": tone,
        "trend": {
            "views": view_series,
            "viewsInPeriod": sum(p["count"] for p in view_series),
            "viewsTotal": article.view_count,
            "direction": analysis.direction(view_series),
            "likes": analysis.daily_series(likes, today, DAYS),
            "comments": analysis.daily_series(comments, today, DAYS),
        },
        "topic": {
            "name": category.name if category else None,
            "slug": category.slug if category else None,
            "weekly": analysis.weekly([p.published_at.date() for p in peers if p.published_at], today, WEEKS),
            "tone": topic_tone,
            "toneLabel": analysis.band(topic_tone)[1] if topic_tone is not None else None,
            "articles": len(peers),
        },
    })
