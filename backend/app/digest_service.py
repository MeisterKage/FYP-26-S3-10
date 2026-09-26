"""Compiling, storing and presenting monthly digests.

The ranking rules are pure and live in `digest.py`. This module reads the
month's articles and corrections, stores each edition with its ranked entries,
notifies subscribers once per new edition, and shows readers what has
happened to an article since the edition went out.
"""
from __future__ import annotations

import calendar
import json
from datetime import datetime

from . import digest
from .countries import country_name
from .enums import ArticleStatus
from .extensions import db
from .models import (
    Article, Category, Correction, DigestEdition, DigestEntry, DigestSubscription,
    Notification, utcnow,
)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        from datetime import timezone
        return dt.replace(tzinfo=timezone.utc)
    return dt


def month_label(month: str) -> str:
    year, mon = month.split("-")
    return f"{calendar.month_name[int(mon)]} {year}"


def topic_label(category_name: str, country_code: str) -> str:
    if not country_code:
        return category_name
    return f"{category_name} in {country_name(country_code) or country_code}"


def edition_title(edition: DigestEdition, category: Category) -> str:
    return f"{topic_label(category.name, edition.country_code)}, {month_label(edition.month)}"


# --------------------------------------------------------------------------- #
#  Compiling
# --------------------------------------------------------------------------- #

def is_final(edition: DigestEdition) -> bool:
    """Compiled after its month ended. Earlier compilations are provisional."""
    _, end = digest.parse_month(edition.month)
    return _aware(edition.compiled_at) >= end


def compile_month(month: str, *, force: bool = False, now: datetime | None = None) -> dict:
    """Compile every edition with enough articles for one month. Commits.

    An edition compiled before its month is over is provisional ("in
    progress"), and is recompiled automatically by the next run after the
    month ends. A final edition is left alone unless `force` is set.

    Subscribers are notified once per edition, when it first becomes final:
    never for a half-month edition, and never twice.
    """
    now = now or utcnow()
    start, end = digest.parse_month(month)
    final_now = now >= end

    articles = Article.query.filter(
        Article.status == ArticleStatus.PUBLISHED,
        Article.published_at >= start,
        Article.published_at < end,
    ).all()
    corrections = (
        db.session.query(Correction, Article)
        .join(Article, Article.id == Correction.article_id)
        .filter(Correction.created_at >= start, Correction.created_at < end)
        .all()
    )

    groups: dict[tuple[int, str], list[Article]] = {}
    for a in articles:
        groups.setdefault((a.category_id, ""), []).append(a)
        if a.country_code:
            groups.setdefault((a.category_id, a.country_code), []).append(a)

    result = {"month": month, "created": [], "recompiled": [], "unchanged": [], "notified": 0}
    categories = {
        c.id: c for c in Category.query.filter_by(deleted_at=None, is_system=False)
    }

    for (category_id, country), members in sorted(groups.items(), key=lambda g: (g[0][0], g[0][1])):
        category = categories.get(category_id)
        if category is None:
            continue
        in_topic = [
            (c, a) for c, a in corrections
            if a.category_id == category_id and (not country or a.country_code == country)
        ]
        edition = digest.compile_edition(
            [digest.Candidate(a.id, a.contributor_id, a.credibility_score or 0.0,
                              _aware(a.published_at)) for a in members],
            [digest.CorrectionRecord(a.id, a.title, c.correction_type.value, c.reason,
                                     _aware(c.created_at), c.overturned_at is not None)
             for c, a in in_topic],
        )
        if edition is None:
            continue

        key = digest.edition_key(category.slug, country)
        existing = DigestEdition.query.filter_by(month=month, key=key).first()
        was_final = existing is not None and is_final(existing)
        if was_final and not force:
            result["unchanged"].append(key)
            continue

        row = existing or DigestEdition(
            month=month, key=key, category_id=category_id, country_code=country
        )
        row.data = json.dumps({"stats": edition.stats, "corrections": edition.corrections})
        row.compiled_at = now
        if existing is not None:
            # Delete before inserting: the unit of work would otherwise insert
            # the new entries first and trip the (edition, article) uniqueness.
            DigestEntry.query.filter_by(edition_id=row.id).delete()
            db.session.flush()
            db.session.expire(row, ["entries"])
        row.entries = [
            DigestEntry(article_id=c.article_id, rank=i + 1, score_at_compile=c.credibility)
            for i, c in enumerate(edition.ranked)
        ]
        if existing is None:
            db.session.add(row)
            db.session.flush()
            result["created"].append(key)
        else:
            result["recompiled"].append(key)
        if final_now and not was_final:
            result["notified"] += _notify_subscribers(row, category)

    if final_now:
        # A provisional edition whose topic no longer has enough articles (one
        # was taken down before the month ended) would otherwise stay "in
        # progress" for ever. It never became final, so nobody was notified.
        touched = set(result["created"]) | set(result["recompiled"]) | set(result["unchanged"])
        for stale in DigestEdition.query.filter_by(month=month).all():
            if stale.key not in touched and not is_final(stale):
                db.session.delete(stale)
                result.setdefault("withdrawn", []).append(stale.key)

    db.session.commit()
    return result


def _notify_subscribers(edition: DigestEdition, category: Category) -> int:
    subscribers = DigestSubscription.query.filter_by(
        category_id=edition.category_id, country_code=edition.country_code
    ).all()
    title = edition_title(edition, category)
    for sub in subscribers:
        db.session.add(Notification(
            user_id=sub.user_id,
            # Matches the "monthly_digest" email toggle in account settings.
            event_type="monthly_digest",
            title=f"New digest: {title}",
            body="The month's most credible reporting, and what was corrected.",
            link=f"/digests/{edition.month}/{edition.key}",
        ))
    return len(subscribers)


# --------------------------------------------------------------------------- #
#  Presenting
# --------------------------------------------------------------------------- #

def _since(entry: DigestEntry, compiled_at: datetime) -> str | None:
    """What has happened to an article since the edition was compiled, if anything."""
    article = entry.article
    if article.status == ArticleStatus.RETRACTED:
        return "Retracted since this digest was compiled."
    if article.status != ArticleStatus.PUBLISHED:
        return "No longer published."
    later = [
        c for c in article.corrections
        if c.overturned_at is None and _aware(c.created_at) > _aware(compiled_at)
    ]
    if later:
        first = min(_aware(c.created_at) for c in later)
        return f"Corrected on {first.day} {calendar.month_name[first.month]} {first.year}."
    return None


def summary(edition: DigestEdition, category: Category) -> dict:
    data = json.loads(edition.data)
    return {
        "id": edition.id,
        "month": edition.month,
        "monthLabel": month_label(edition.month),
        "key": edition.key,
        "title": edition_title(edition, category),
        "topic": topic_label(category.name, edition.country_code),
        "category": {"id": category.id, "name": category.name, "slug": category.slug},
        "country": (
            {"code": edition.country_code, "name": country_name(edition.country_code)}
            if edition.country_code else None
        ),
        "stats": data["stats"],
        "compiledAt": edition.compiled_at.isoformat(),
        # Compiled before the month ended: the final edition follows.
        "provisional": not is_final(edition),
    }


def full(edition: DigestEdition, category: Category, viewer=None) -> dict:
    from .modules.articles import serialize

    data = json.loads(edition.data)
    entries = []
    for entry in edition.entries:
        note = _since(entry, edition.compiled_at)
        public = entry.article.status in (ArticleStatus.PUBLISHED, ArticleStatus.RETRACTED)
        entries.append({
            "rank": entry.rank,
            "scoreAtCompile": entry.score_at_compile,
            "since": note,
            # An article taken down since is named, but not served.
            "article": (
                serialize(entry.article, include_body=False, viewer=viewer) if public
                else {"id": entry.article.id, "title": entry.article.title}
            ),
            "available": public,
        })
    subscribed = False
    if viewer is not None:
        subscribed = DigestSubscription.query.filter_by(
            user_id=viewer.id, category_id=edition.category_id,
            country_code=edition.country_code,
        ).first() is not None
    return {
        **summary(edition, category),
        "entries": entries,
        "corrections": data["corrections"],
        "subscribed": subscribed,
    }
