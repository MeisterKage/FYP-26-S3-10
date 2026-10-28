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
from datetime import datetime, timedelta

from flask import current_app

from . import source_rating
from .extensions import db
from .models import Article, ArticleSource, AuditLog, DomainLookup, SourceDomainRule, utcnow

log = logging.getLogger(__name__)

CROSSREF = "https://api.crossref.org/v1/works/"
CROSSREF_TIMEOUT = 8
#: Crossref asks API users to identify themselves; this puts requests in its
#: faster "polite" pool.
CROSSREF_AGENT = "SterlingWire-SourceRatings/1.0 (+https://fyp-26-s3-10-web.onrender.com)"
#: Kinds of fetch failure meaning "there is no such page". Anything else (a
#: site blocking scripts, a timeout) says nothing against the source.
MISSING = {"missing", "refused"}
RETRACTION_TYPES = {"retraction", "withdrawal", "removal"}

WIKIDATA = "https://query.wikidata.org/sparql"
WIKIDATA_TIMEOUT = 20
#: Wikidata classes that make an organisation an official source: government
#: agency, government organisation, legislature, court, central bank,
#: intergovernmental organisation, ministry. Matched through subclasses.
OFFICIAL_CLASSES = ("Q327333", "Q2659904", "Q11204", "Q41487", "Q66344", "Q245065", "Q192350")
#: Classes that disqualify an organisation even if it is also a government
#: body: mass media, broadcaster, news media, public broadcaster, newspaper. A
#: public broadcaster such as the ABC is government-funded, but its reporting is
#: journalism, not an official statement.
MEDIA_CLASSES = ("Q11033", "Q15265344", "Q1193236", "Q1126006", "Q11032")
LOOKUP_TTL = timedelta(days=30)
LOOKUP_ERROR_TTL = timedelta(days=1)


def _wikidata_query(domain: str) -> list[dict]:
    """Organisations whose official website is this domain, each marked official or media.

    The domain goes into the query only as part of fixed URL forms, after
    normalise_domain has reduced it to letters, digits, dots and hyphens, so it
    cannot change the query's meaning.
    """
    sites = " ".join(f"<{scheme}://{www}{domain}{slash}>"
                     for scheme in ("https", "http") for www in ("www.", "") for slash in ("/", ""))
    official = " ".join(f"wd:{q}" for q in OFFICIAL_CLASSES)
    media = " ".join(f"wd:{q}" for q in MEDIA_CLASSES)
    query = f"""SELECT DISTINCT ?item ?itemLabel ?kind WHERE {{
      VALUES ?site {{ {sites} }}
      ?item wdt:P856 ?site .
      {{ VALUES ?c {{ {official} }} ?item wdt:P31/wdt:P279* ?c . BIND("official" AS ?kind) }}
      UNION
      {{ VALUES ?m {{ {media} }} ?item wdt:P31/wdt:P279* ?m . BIND("media" AS ?kind) }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT 50"""
    request = urllib.request.Request(
        WIKIDATA + "?" + urllib.parse.urlencode({"query": query}),
        headers={"User-Agent": CROSSREF_AGENT, "Accept": "application/sparql-results+json"},
    )
    with urllib.request.urlopen(request, timeout=WIKIDATA_TIMEOUT) as response:
        return json.loads(response.read(2_000_000))["results"]["bindings"]


def official_owner(domain: str, now: datetime, *, fetch: bool) -> str | None:
    """The government body that owns a domain, per Wikidata, cached. None if none.

    An organisation counts only if Wikidata records it as a government body
    and not also as a media organisation.
    """
    domain = source_rating.normalise_domain(domain)
    if not domain:
        return None
    cached = DomainLookup.query.filter_by(domain=domain).first()
    if cached is not None:
        ttl = LOOKUP_ERROR_TTL if cached.status == "error" else LOOKUP_TTL
        if _aware(cached.checked_at) > now - ttl:
            return cached.owner if cached.status == "official" else None
    if not fetch:
        return None

    row = cached or DomainLookup(domain=domain)
    try:
        bindings = _wikidata_query(domain)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError):
        row.status, row.owner, row.wikidata_id = "error", None, None
    else:
        kinds: dict[str, set] = {}
        labels: dict[str, str] = {}
        for b in bindings:
            qid = b["item"]["value"].rsplit("/", 1)[-1]
            kinds.setdefault(qid, set()).add(b["kind"]["value"])
            labels[qid] = b.get("itemLabel", {}).get("value", qid)
        official = sorted(q for q, k in kinds.items() if k == {"official"})
        if official:
            row.status, row.wikidata_id, row.owner = "official", official[0], labels[official[0]][:300]
        else:
            row.status, row.owner, row.wikidata_id = "none", None, None
    row.checked_at = now
    if cached is None:
        db.session.add(row)
    return row.owner if row.status == "official" else None


def admin_rules() -> dict[str, tuple[str, str]]:
    return {r.domain: (r.tier, r.reason) for r in SourceDomainRule.query.all()}


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        from datetime import timezone
        return dt.replace(tzinfo=timezone.utc)
    return dt


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

    rules = admin_rules()
    seen: set[str] = set()
    for source in sources:
        snap = pages.get(source.url)
        exists = None if snap is None else snap.status not in MISSING
        facts = dict(exists=exists, admin_rules=rules,
                     doi_status=statuses.get(dois[source.id]) if dois[source.id] else None)
        rating = source_rating.classify(source.url, **facts)
        if rating.tier == "unrated":
            # Nothing else decided it: ask who owns the domain. Only here, so
            # Wikidata is consulted for the few domains the lists miss.
            owner = official_owner(source_rating.host_of(source.url), now, fetch=fetch_sources)
            if owner:
                rating = source_rating.classify(source.url, official_owner=owner, **facts)
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


def regrade_domain(domain: str) -> int:
    """Re-grade every article citing a domain, after an administrator changes its rule.

    Uses cached page checks only, so an administrator is not left waiting on
    the network. Returns how many articles were re-graded. Does not commit.
    """
    from .scoring_service import rescore_article

    domain = source_rating.normalise_domain(domain)
    articles = {}
    for source in ArticleSource.query.filter(ArticleSource.url.ilike(f"%{domain}%")).all():
        host = source_rating.host_of(source.url)
        if host == domain or host.endswith("." + domain):
            articles[source.article_id] = source.article
    for article in articles.values():
        rate_sources(article, fetch_sources=False)
        if article.status.value in ("published", "retracted"):
            rescore_article(article)
    return len(articles)


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
