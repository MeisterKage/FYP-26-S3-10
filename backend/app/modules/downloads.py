"""Download an article as a PDF or a PowerPoint deck.

    GET /articles/<slug>/download.pdf
    GET /articles/<slug>/download.pptx

A published article, or a writer's own. A subscriber-only article only for a
reader who may open it: the file is the whole text.
"""
from __future__ import annotations

import re

from flask import Blueprint, Response

from .. import exports
from ..enums import ArticleStatus
from ..errors import ApiError
from ..insights_service import in_brief
from ..models import Article
from ..security import current_user
from ..translation_service import fresh, points as translated_points, request_lang
from .articles import list_loads, may_read
from .share import article_url

bp = Blueprint("downloads", __name__)

TYPES = {
    "pdf": ("application/pdf", exports.to_pdf),
    "pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation",
             exports.to_pptx),
}


#: The fixed words in a download, per language.
LABELS = {
    "zh": {"in_brief": "要点", "credibility": "可信度评分", "sources": "资料来源",
           "approved_by": "审核编辑：", "downloaded": "下载自", "read_online": "在线阅读，查看来源与更正",
           "sourcing": "来源与评分", "summary_note": "人工智能生成"},
    "ms": {"in_brief": "Ringkasan", "credibility": "Skor kredibiliti", "sources": "Sumber",
           "approved_by": "Diluluskan oleh", "downloaded": "Dimuat turun daripada",
           "read_online": "Baca dalam talian, bersama sumber dan pembetulan",
           "sourcing": "Sumber dan skor", "summary_note": "Dijana oleh AI"},
}


def content_for(article: Article, lang: str = "en") -> exports.ExportContent:
    published = article.published_at
    dateline = " · ".join(x for x in [
        f"{published.day} {published.strftime('%B %Y')}" if published else "",
        article.country_code or "",
    ] if x)
    brief = in_brief(article)
    reviewer = article.reviewer.byline if article.reviewer and not article.awaiting_review else None
    translation = fresh(article, lang) if lang != "en" else None
    points = brief["points"] if brief else []
    if translation is not None:
        points = translated_points(translation) or points
    return exports.ExportContent(
        title=translation.title if translation else article.title,
        summary=(translation.summary if translation else article.summary) or "",
        body_html=translation.body if translation else article.body,
        lang=lang if translation else "en",
        labels=LABELS.get(lang, {}) if translation else {},
        byline=article.contributor.byline,
        dateline=dateline,
        score=article.credibility_score if article.status == ArticleStatus.PUBLISHED else None,
        band=article.credibility_band,
        approved_by=reviewer,
        url=article_url(article),
        points=points,
        sources=[(s.label or s.url, s.url) for s in article.sources if s.is_valid],
    )


@bp.get("/articles/<slug>/download.<kind>")
def download(slug: str, kind: str):
    if kind not in TYPES:
        raise ApiError("Downloads are available as PDF or PowerPoint.", status=404)
    article = Article.query.options(*list_loads()).filter_by(slug=slug).first()
    viewer = current_user()
    own = viewer is not None and article is not None and viewer.id == article.contributor_id
    if article is None or (article.status != ArticleStatus.PUBLISHED and not own):
        raise ApiError("Article not found.", status=404)
    if not may_read(article, viewer):
        raise ApiError("This article is for subscribers. Subscribe to download it.", status=403)

    mimetype, build = TYPES[kind]
    data = build(content_for(article, request_lang()))
    name = re.sub(r"[^a-z0-9]+", "-", article.title.lower()).strip("-")[:80] or "article"
    response = Response(data, mimetype=mimetype)
    response.headers["Content-Disposition"] = f'attachment; filename="{name}.{kind}"'
    return response
