"""Rating an article's cited sources, and an editor's verdict on them.

The rules are pure and live in `source_rating.py`. This module supplies the
facts they need: whether each page exists (through the same safe fetcher and
cache the originality check uses) and, for a paper, whether Crossref and
Retraction Watch record it as retracted.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from flask import current_app

from . import source_rating
from .extensions import db
from .models import Article, ArticleSource, AuditLog, utcnow

log = logging.getLogger(__name__)

CROSSREF = "https://api.crossref.org/v1/works/"
CROSSREF_TIMEOUT = 8
#: Crossref asks API users to identify themselves; this puts requests in its
#: faster "polite" pool.
CROSSREF_AGENT = "WollongongNews-SourceRatings/1.0 (+https://fyp-26-s3-10-web.onrender.com)"
#: Kinds of fetch failure meaning "there is no such page". Anything else (a
#: site blocking scripts, a timeout) says nothing against the source.
MISSING = {"missing", "refused"}
RETRACTION_TYPES = {"retraction", "withdrawal", "removal"}


def crossref_status(doi: str) -> str | None:
    """"ok", "retracted", "unknown" (no such paper), or None if Crossref could not be asked.

    The host is fixed, so this is not a server-side request forgery risk, and
    the DOI is URL-encoded into the path.
    """
    url = CROSSREF + urllib.parse.quote(doi, safe="")
    request = urllib.request.Request(url, headers={"User-Agent": CROSSREF_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=CROSSREF_TIMEOUT) as response:
            message = json.loads(response.read(2_000_000))["message"]
    except urllib.error.HTTPError as e:
        return "unknown" if e.code == 404 else None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError):
        return None
    notices = message.get("updated-by") or []
    if any(n.get("type") in RETRACTION_TYPES for n in notices):
        return "retracted"
    return "ok"


def rate_sources(article: Article, *, now: datetime | None = None,
                 fetch_sources: bool | None = None) -> list[ArticleSource]:
    """Rate every source on an article and store the results. Does not commit.

    Editor verdicts survive re-rating: a source an editor accepted stays
    accepted if the article is resubmitted, and the new rating is shown
    alongside it.
    """
    from .originality_service import fetch_pages

    now = now or utcnow()
    if fetch_sources is None:
        fetch_sources = current_app.config.get("ORIGINALITY_FETCH_SOURCES", True)

    sources = list(article.sources)
    pages = fetch_pages([s.url for s in sources], now, fetch_sources=fetch_sources)

    dois = {s.id: source_rating.doi_of(s.url) for s in sources}
    wanted = sorted({d for d in dois.values() if d})
    statuses: dict[str, str | None] = {}
    if wanted and fetch_sources:
        with ThreadPoolExecutor(max_workers=min(4, len(wanted))) as pool:
            statuses = dict(zip(wanted, pool.map(crossref_status, wanted)))

    seen: set[str] = set()
    for source in sources:
        snap = pages.get(source.url)
        exists = None if snap is None else snap.status not in MISSING
        rating = source_rating.classify(
            source.url, exists=exists,
            doi_status=statuses.get(dois[source.id]) if dois[source.id] else None,
        )
        key = source.url.strip().rstrip("/").lower()
        if key in seen:
            # The same link cited twice earns its points once.
            rating = source_rating.Rating("invalid", 0.0, "The same link is already cited above.")
        seen.add(key)

        source.tier = rating.tier
        source.points = rating.points
        source.rating_reason = rating.reason[:400]
        source.flagged = rating.flagged
        source.rated_at = now
        source.is_valid = source_rating.points_for(rating, source.editor_verdict) > 0
    return sources


def source_points(source: ArticleSource, default: float) -> float:
    """Points one source contributes to the score.

    An unrated source (added before ratings existed, and not yet re-rated)
    scores as it always did, so nothing changes until it is rated.
    """
    if source.tier is None:
        return default if source.is_valid else 0.0
    if source.editor_verdict == "accepted":
        return source_rating.FULL
    if source.editor_verdict == "rejected":
        return source_rating.NONE
    return source.points or 0.0


def apply_verdict(source: ArticleSource, *, verdict: str | None, reason: str | None,
                  editor_id: int, now: datetime | None = None) -> None:
    """Record an editor's final word on a source. None clears it. Does not commit."""
    now = now or utcnow()
    source.editor_verdict = verdict
    source.editor_reason = reason
    source.editor_id = editor_id if verdict else None
    source.verdict_at = now if verdict else None
    if source.tier is not None:
        rating = source_rating.Rating(source.tier, source.points or 0.0, source.rating_reason or "")
        source.is_valid = source_rating.points_for(rating, verdict) > 0
    else:
        source.is_valid = verdict != "rejected"
    db.session.add(AuditLog(
        actor_id=editor_id, action=f"source.{verdict or 'verdict_cleared'}",
        entity_type="article_source", entity_id=source.id,
        detail=f"{source.url[:200]} :: {reason or ''}"[:500],
    ))


def serialize(source: ArticleSource) -> dict:
    return {
        "id": source.id,
        "url": source.url,
        "label": source.label,
        "isValid": source.is_valid,
        "rating": None if source.tier is None else {
            "tier": source.tier,
            "label": source_rating.TIER_LABELS.get(source.tier, source.tier),
            "points": source_points(source, source_rating.FULL),
            "reason": source.rating_reason,
            "flagged": source.flagged,
            "editorVerdict": source.editor_verdict,
            "editorReason": source.editor_reason,
        },
    }
