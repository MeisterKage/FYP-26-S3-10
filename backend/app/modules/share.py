"""Link previews for shared articles.

The website is a single-page app: every address serves the same empty HTML
shell, filled in by JavaScript. Link-preview crawlers (WhatsApp, Facebook, X,
Telegram, LinkedIn, iMessage) do not run JavaScript, so a shared article link
showed no headline and no picture.

The share buttons therefore point here. This page carries the article's
Open Graph tags (headline, summary with its credibility score, cover image),
which crawlers read, and forwards people straight on to the article itself.
Nothing about hosting changes: it is one more route on the existing API.
"""
from __future__ import annotations

import io

from flask import Blueprint, Response, current_app, request
from markupsafe import escape
from PIL import Image

from ..enums import ArticleStatus
from ..errors import ApiError
from ..extensions import db
from ..models import Article, ArticleImage

bp = Blueprint("share", __name__)

SITE = "Wollongong News"


def site_url() -> str:
    return current_app.config["SITE_URL"].rstrip("/")


def article_url(article: Article) -> str:
    return f"{site_url()}/articles/{article.slug}"


def share_page_url(article: Article) -> str:
    return f"{request.host_url.rstrip('/')}/api/share/{article.slug}"


def _description(article: Article) -> str:
    score = article.credibility_score
    rating = (f"Credibility score {round(score)}/100"
              + (f", {article.credibility_band}" if article.credibility_band else "")
              if score is not None else "")
    parts = [p for p in ((article.summary or "").strip(), rating) if p]
    return " · ".join(parts)


@bp.get("/share/<slug>")
def share_page(slug: str):
    article = Article.query.filter_by(slug=slug, status=ArticleStatus.PUBLISHED).first()
    target = article_url(article) if article else f"{site_url()}/"
    if article is None:
        body = (f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" '
                f'content="0; url={escape(target)}"><title>{SITE}</title>'
                f'<p><a href="{escape(target)}">{SITE}</a></p>')
        return Response(body, status=404, mimetype="text/html")

    title = escape(article.title)
    description = escape(_description(article))
    image_tags = ""
    if article.cover_image is not None:
        image = f"{request.host_url.rstrip('/')}/api/images/{article.cover_image.key}/share.jpg"
        alt = escape(article.cover_image_alt or article.title)
        image_tags = (
            f'<meta property="og:image" content="{escape(image)}">'
            f'<meta property="og:image:type" content="image/jpeg">'
            f'<meta property="og:image:width" content="{article.cover_image.width}">'
            f'<meta property="og:image:height" content="{article.cover_image.height}">'
            f'<meta property="og:image:alt" content="{alt}">'
            f'<meta name="twitter:image" content="{escape(image)}">'
        )
    published = article.published_at.isoformat() if article.published_at else ""
    url = escape(target)
    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title} · {SITE}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{url}">
<meta property="og:site_name" content="{SITE}">
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{url}">
<meta property="article:published_time" content="{escape(published)}">
<meta name="twitter:card" content="{'summary_large_image' if image_tags else 'summary'}">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
{image_tags}
<meta http-equiv="refresh" content="0; url={url}">
</head>
<body>
<p><a href="{url}">{title}</a> on {SITE}</p>
</body>
</html>"""
    response = Response(body, mimetype="text/html")
    # Crawlers and people may cache this briefly; a score change shows within minutes.
    response.headers["Cache-Control"] = "public, max-age=600"
    return response


@bp.get("/images/<key>/share.jpg")
def share_image(key: str):
    """The cover as a JPEG: every preview crawler reads JPEG, not all read WebP."""
    row = db.session.query(ArticleImage.large).filter(ArticleImage.key == key).first()
    if row is None:
        raise ApiError("Image not found.", status=404)
    with Image.open(io.BytesIO(row[0])) as source:
        out = io.BytesIO()
        source.convert("RGB").save(out, format="JPEG", quality=82, optimize=True)
    response = Response(out.getvalue(), mimetype="image/jpeg")
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response
