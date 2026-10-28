"""Originality checks against this platform's articles and each article's cited sources.

The pure comparison lives in `originality.py`; this module supplies it with
data: the fingerprint index, cited pages (fetched safely by `source_fetch.py`
and cached as SourceSnapshot rows), and the thresholds an administrator set.

What is compared, and what is not:

  * Every other submitted article on the platform (published, pending,
    scheduled, unpublished or retracted). Drafts and rejected articles are the
    writer's private work and are not part of the index anyone is checked
    against.
  * The pages the article itself cites. Copying a source word for word without
    quotation marks is the most common plagiarism in news, and no general
    checker knows which pages an article cites.
  * Not the open web. That needs a commercial index; see docs for the provider
    seam. Reports say so rather than implying a clean result means "original
    everywhere".
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from hashlib import sha256

from flask import current_app
from sqlalchemy import func

from . import originality as engine
from .enums import ArticleStatus, Role
from .extensions import db
from .models import Article, ArticleFingerprint, SourceSnapshot, utcnow
from .source_fetch import SourceUnavailable, fetch

#: Articles other submissions are compared against.
CORPUS_STATUSES = (
    ArticleStatus.PUBLISHED, ArticleStatus.PENDING, ArticleStatus.SCHEDULED,
    ArticleStatus.UNPUBLISHED, ArticleStatus.RETRACTED,
)
#: Statuses a reader can see, so a match's title and text may be shown to anyone.
PUBLIC_STATUSES = (ArticleStatus.PUBLISHED, ArticleStatus.RETRACTED)

MAX_SOURCES_CHECKED = 10
SNAPSHOT_TTL = timedelta(days=7)
MAX_MATCHES_REPORTED = 8
#: Candidates found through the fingerprint index that are then measured
#: exactly. The index finds likely matches; exact measurement against the full
#: text gives the percentage, because a winnowed sample loses words at the
#: edges of a passage.
MAX_CANDIDATES_MEASURED = 20
#: Matches below this are common phrasing rather than borrowed text.
MIN_MATCH_PERCENT = 2.0
REPORT_VERSION = 1


# --------------------------------------------------------------------------- #
#  Index
# --------------------------------------------------------------------------- #

def index_article(article: Article) -> None:
    """Rewrite an article's fingerprints. Call whenever its body changes. Does not commit."""
    if article.id is None:
        db.session.flush()
    ArticleFingerprint.query.filter_by(article_id=article.id).delete()
    doc = engine.parse(article.body or "")
    db.session.add_all(
        ArticleFingerprint(article_id=article.id, hash=h, position=p)
        for h, p in engine.fingerprint(doc)
    )


def reindex_all() -> int:
    count = 0
    for article in Article.query.all():
        index_article(article)
        count += 1
    db.session.commit()
    return count


def _first_seen():
    """When an article's text first entered the platform: submission, else publication, else creation."""
    return func.coalesce(Article.submitted_at, Article.published_at, Article.created_at)


def _reference_time(article: Article, now: datetime) -> datetime:
    """The moment this article's text is being judged at.

    A draft or a rejected article is being checked for (re)submission now. A
    submitted or published one is judged as of when it was first submitted,
    so a later copy of it can never make the original look copied.
    """
    if article.status in (ArticleStatus.DRAFT, ArticleStatus.REJECTED):
        return now
    return article.submitted_at or article.published_at or article.created_at or now


def _candidates(article: Article, hashes: set[int], before: datetime) -> dict[int, set[int]]:
    """Earlier indexed articles sharing any fingerprint, with the hashes they share.

    Only articles that entered the platform before this one: when text is shared,
    the earlier article is the original and the later one is the copy.
    """
    found: dict[int, set[int]] = {}
    values = list(hashes)
    for i in range(0, len(values), 500):
        rows = (
            db.session.query(ArticleFingerprint.article_id, ArticleFingerprint.hash)
            .join(Article, Article.id == ArticleFingerprint.article_id)
            .filter(
                ArticleFingerprint.hash.in_(values[i:i + 500]),
                ArticleFingerprint.article_id != article.id,
                Article.status.in_(CORPUS_STATUSES),
                _first_seen() < before,
            )
            .all()
        )
        for article_id, h in rows:
            found.setdefault(article_id, set()).add(h)
    return found


# --------------------------------------------------------------------------- #
#  Cited sources
# --------------------------------------------------------------------------- #

def _url_key(url: str) -> str:
    return sha256(url.encode()).hexdigest()


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        from datetime import timezone
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _fetch_one(url: str) -> tuple[str, str | None, str | None, str]:
    """(url, text, error, status). Runs in a worker thread: no database access here."""
    try:
        page = fetch(url)
    except SourceUnavailable as e:
        return url, None, str(e), e.kind
    except Exception:  # noqa: BLE001 - a broken page must not break the check
        return url, None, "The page could not be read.", "unreachable"
    html = "html" in page.content_type
    text = engine.parse(page.body, html=html).text
    return url, text, None, "ok"


def fetch_pages(urls: list[str], now: datetime, *, fetch_sources: bool) -> dict:
    """SourceSnapshot rows for these URLs: cached if fresh, otherwise fetched in parallel.

    Shared by the originality check, which compares text, and source rating,
    which needs to know whether a page exists. A snapshot's status is "ok" or
    one of the kinds SourceUnavailable reports. A URL that is not cached, while
    fetching is off, is absent from the result.
    """
    found = {}
    to_fetch = []
    for url in dict.fromkeys(urls):
        snap = SourceSnapshot.query.filter_by(url_hash=_url_key(url)).first()
        if snap is not None and _aware(snap.fetched_at) > now - SNAPSHOT_TTL:
            found[url] = snap
        elif fetch_sources:
            to_fetch.append(url)
    if to_fetch:
        # In parallel, so ten slow sources cost one timeout, not ten.
        with ThreadPoolExecutor(max_workers=min(6, len(to_fetch))) as pool:
            results = list(pool.map(_fetch_one, to_fetch))
        for url, text, error, status in results:
            snap = SourceSnapshot.query.filter_by(url_hash=_url_key(url)).first()
            if snap is None:
                snap = SourceSnapshot(url_hash=_url_key(url), url=url[:1000])
                db.session.add(snap)
            snap.status = status
            snap.error = error
            snap.text = text
            snap.fetched_at = now
            found[url] = snap
    return found


def source_documents(article: Article, now: datetime, *, fetch_sources: bool):
    """Cited pages as parsed documents, plus a status line for every source."""
    valid = [s for s in article.sources if s.is_valid]
    sources, skipped = valid[:MAX_SOURCES_CHECKED], valid[MAX_SOURCES_CHECKED:]
    pages = fetch_pages([s.url for s in sources], now, fetch_sources=fetch_sources)

    lines, docs = [], {}
    for s in sources:
        snap = pages.get(s.url)
        if snap is None:
            lines.append({"url": s.url, "label": s.label, "status": "skipped",
                          "reason": "Source checking is switched off."})
        elif snap.status == "ok":
            docs[s.url] = engine.parse(snap.text or "", html=False)
            lines.append({"url": s.url, "label": s.label, "status": "checked"})
        else:
            lines.append({"url": s.url, "label": s.label, "status": "unavailable",
                          "reason": snap.error})
    lines += [
        {"url": s.url, "label": s.label, "status": "skipped",
         "reason": f"Only the first {MAX_SOURCES_CHECKED} sources are checked."}
        for s in skipped
    ]
    return docs, lines


# --------------------------------------------------------------------------- #
#  The check
# --------------------------------------------------------------------------- #

def _other_excerpt(other: engine.Document, matched_hashes: list[int]) -> str:
    grams = engine.kgrams(other.tokens)
    first: dict[int, int] = {}
    for i, h in enumerate(grams):
        first.setdefault(h, i)
    positions = [first[h] for h in matched_hashes if h in first]
    if not positions:
        return ""
    a, b = min(positions), min(max(positions) + engine.K - 1, len(other.tokens) - 1)
    return other.text[other.tokens[a].start:other.tokens[b].end][:600]


def _passage_list(doc, positions, other_doc=None) -> list[dict]:
    hashes = engine.kgrams(doc.tokens)
    out = []
    for p in engine.passages(doc, positions)[:12]:
        entry = {"text": p.text[:600]}
        if other_doc is not None:
            run = [hashes[i] for i in positions
                   if doc.tokens[i].start >= p.start and doc.tokens[i].start < p.end]
            entry["otherText"] = _other_excerpt(other_doc, run)
        out.append(entry)
    return out


def check(article: Article, *, settings: dict | None = None, now: datetime | None = None,
          fetch_sources: bool | None = None) -> dict:
    """Run the full check and store the result on the article. Does not commit."""
    now = now or utcnow()
    if fetch_sources is None:
        fetch_sources = current_app.config.get("ORIGINALITY_FETCH_SOURCES", True)

    doc = engine.parse(article.body or "")
    own_hashes = set(engine.kgrams(doc.tokens))
    matches: list[dict] = []
    all_positions: set[int] = set()

    # ---- other articles on the platform ----
    found = _candidates(article, own_hashes, _reference_time(article, now))
    likely = sorted(found, key=lambda i: -len(found[i]))[:MAX_CANDIDATES_MEASURED]
    measured = []
    for other_id in likely:
        other = db.session.get(Article, other_id)
        other_doc = engine.parse(other.body or "")
        positions = engine.matched_positions(doc, set(engine.kgrams(other_doc.tokens)))
        percent = engine.coverage(doc, positions)
        if percent < MIN_MATCH_PERCENT:
            continue
        all_positions |= positions
        measured.append((percent, other, other_doc, positions))

    measured.sort(key=lambda m: -m[0])
    for percent, other, other_doc, positions in measured[:MAX_MATCHES_REPORTED]:
        m = {"kind": "article", "articleId": other.id, "percent": percent}
        matches.append(m)
        m.update({
            "title": other.title,
            "slug": other.slug,
            "status": other.status.value,
            "public": other.status in PUBLIC_STATUSES,
            "sameWriter": other.contributor_id == article.contributor_id,
            "passages": _passage_list(doc, positions, other_doc),
        })

    # ---- the article's own cited sources ----
    source_docs, source_lines = source_documents(article, now, fetch_sources=fetch_sources)
    labels = {s.url: s.label for s in article.sources}
    # A licensed republication matches its original word for word, by design.
    # That is the one source it is allowed to copy, so it is reported as the
    # original rather than counted as copying.
    republished = json.loads(article.republication) if article.republication else None
    original_url = republished.get("url") if republished else None
    for url, src in source_docs.items():
        if original_url and url.rstrip("/") == original_url.rstrip("/"):
            continue
        positions = engine.matched_positions(doc, set(engine.kgrams(src.tokens)))
        percent = engine.coverage(doc, positions)
        if percent < MIN_MATCH_PERCENT:
            continue
        all_positions |= positions
        matches.append({
            "kind": "source", "url": url, "label": labels.get(url), "percent": percent,
            "passages": _passage_list(doc, positions, src),
        })

    percent = engine.coverage(doc, all_positions)
    report = {
        "version": REPORT_VERSION,
        "checkedAt": now.isoformat(),
        "percent": percent,
        "level": engine.level(percent, settings),
        "wordCount": doc.word_count,
        "matches": sorted(matches, key=lambda m: -m["percent"]),
        "sources": source_lines,
        "quotes": engine.verify_quotes(doc, source_docs),
        "republishedFrom": (
            {"publisher": republished.get("publisher"), "url": original_url,
             "licence": republished.get("licence")} if republished else None
        ),
        "scope": "Compared with every article submitted to Sterling Wire and with the "
                 "pages this article cites. The wider web is not searched.",
    }
    article.originality_percent = percent
    article.originality_report = json.dumps(report)
    article.originality_checked_at = now
    return report


def stored_report(article: Article) -> dict | None:
    return json.loads(article.originality_report) if article.originality_report else None


def for_viewer(report: dict | None, article: Article, viewer) -> dict | None:
    """What this viewer may see of a report.

    Editors and administrators see everything. A writer sees their own text
    highlighted, but not the text or title of another writer's unpublished
    submission: a check must not become a way to read someone else's draft.
    """
    if report is None or viewer is None:
        return None
    if viewer.role in (Role.EDITOR, Role.SYSTEM_ADMIN):
        return report
    visible = dict(report)
    visible["matches"] = []
    for m in report["matches"]:
        m = dict(m)
        if m["kind"] == "article" and not m["public"] and not m["sameWriter"]:
            m["title"] = None
            m["slug"] = None
            m["passages"] = [{"text": p["text"]} for p in m["passages"]]
        visible["matches"].append(m)
    return visible


def _settings() -> dict:
    """Admin thresholds, read once per request however many articles are serialised."""
    from flask import g, has_request_context
    from .scoring_service import load_settings

    if not has_request_context():
        return load_settings()
    if "_originality_settings" not in g:
        g._originality_settings = load_settings()
    return g._originality_settings


def summary(article: Article) -> dict | None:
    if article.originality_checked_at is None:
        return None
    return {
        "percent": article.originality_percent,
        "level": engine.level(article.originality_percent or 0.0, _settings()),
        "checkedAt": article.originality_checked_at.isoformat(),
    }
