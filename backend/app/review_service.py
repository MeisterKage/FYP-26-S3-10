"""Database-facing wrapper around the pure triage engine in `triage.py`.

`triage.py` decides; this module gathers the inputs from the database, applies
the decisions, and writes the results back. The split mirrors `credibility.py`
and `scoring_service.py` for the same reason: the rules stay testable without an
application context, and there is exactly one place that touches the database.

It is also the single path by which an article becomes published. Manual
approval, batch approval and auto-publish all go through `publish_article`, so
notifications, scoring and the audit trail cannot drift apart between them.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from . import triage
from .enums import ArticleStatus
from .extensions import db
from .models import Article, AuditLog, Notification, User, utcnow
from .scoring_service import _published_counts, load_settings, rescore_article


def _aware(dt: datetime | None) -> datetime | None:
    """Treat a naive datetime as UTC.

    Postgres returns timezone-aware values for these columns; SQLite, which the
    test suite runs on, drops the zone. Subtracting one kind from the other
    raises, so every comparison here goes through this first.
    """
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def hours_since(dt: datetime | None, now: datetime) -> float:
    dt = _aware(dt)
    if dt is None:
        return 0.0
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def valid_source_count(article: Article) -> int:
    return sum(1 for s in article.sources if s.is_valid)


def has_duplicate_title(article: Article) -> bool:
    # Imported here, not at module level: moderation imports this module for
    # revocation, and a top-level import back would be circular.
    from .modules.moderation import duplicate_titles

    return bool(duplicate_titles(article.title, exclude_article_id=article.id))


def is_suspended(user: User, now: datetime) -> bool:
    until = _aware(user.autopublish_suspended_until)
    return until is not None and until > now


# --------------------------------------------------------------------------- #
#  Queue ordering
# --------------------------------------------------------------------------- #

def priority_for(article: Article, settings: dict, now: datetime) -> triage.PriorityBreakdown:
    return triage.review_priority(
        contributor_accuracy=article.contributor.accuracy_rate,
        source_count=valid_source_count(article),
        has_duplicate_title=has_duplicate_title(article),
        hours_waiting=hours_since(article.submitted_at, now),
        similarity_percent=article.originality_percent,
        settings=settings,
    )


# --------------------------------------------------------------------------- #
#  Publishing
# --------------------------------------------------------------------------- #

def publish_article(
    article: Article,
    *,
    reviewer_id: int | None,
    now: datetime,
    auto: bool = False,
    detail: str | None = None,
):
    """Publish one pending article. Does not commit; the caller owns the unit of work.

    Publishing is when a credibility score first becomes visible, so it is
    computed here rather than lazily on first read.
    """
    article.status = ArticleStatus.PUBLISHED
    article.published_at = now
    article.reviewed_by_id = reviewer_id
    article.rejection_reason = None
    if auto:
        article.auto_published_at = now
        article.review_confirmed_at = None

    breakdown = rescore_article(article)

    if auto:
        title = "Your article was published automatically"
        body = (
            f"'{article.title}' is live. The review queue was backed up, so it was "
            "published before an editor read it. Readers see it marked as not yet "
            "reviewed until an editor confirms it."
        )
    else:
        title = "Your article has been published"
        body = f"'{article.title}' is now live."

    db.session.add(
        Notification(
            user_id=article.contributor_id,
            event_type="article.autopublished" if auto else "article.approved",
            title=title,
            body=body,
            link=f"/articles/{article.slug}",
        )
    )
    db.session.add(
        AuditLog(
            actor_id=reviewer_id,
            action="article.autopublish" if auto else "article.approve",
            entity_type="article",
            entity_id=article.id,
            detail=detail,
        )
    )
    return breakdown


def confirm_article(article: Article, *, reviewer_id: int, now: datetime) -> None:
    """An editor has now read an auto-published article. Clears the reader label."""
    article.review_confirmed_at = now
    article.reviewed_by_id = reviewer_id
    db.session.add(
        AuditLog(
            actor_id=reviewer_id,
            action="article.confirm",
            entity_type="article",
            entity_id=article.id,
        )
    )


# --------------------------------------------------------------------------- #
#  Auto-publish
# --------------------------------------------------------------------------- #

def eligibility_for(article: Article, settings: dict, now: datetime) -> triage.Eligibility:
    published, _ = _published_counts(article.contributor_id)
    if article.originality_percent is None:
        # Submitted before checking existed, or never checked: check now,
        # rather than let an unchecked article through or hold it forever.
        from .originality_service import check
        check(article, settings=settings, now=now)
    return triage.autopublish_eligibility(
        contributor_accuracy=article.contributor.accuracy_rate,
        published_count=published,
        suspended=is_suspended(article.contributor, now),
        source_count=valid_source_count(article),
        has_duplicate_title=has_duplicate_title(article),
        is_premium=article.is_premium,
        similarity_percent=article.originality_percent,
        settings=settings,
    )


def run_autopublish(now: datetime | None = None) -> dict:
    """One sweep of the backlog. Commits.

    Works through the pending queue oldest first, so the longest-waiting eligible
    articles go out before newer ones, and stops at `autopublish_max_per_run` so
    one sweep has a bounded effect however large the backlog.
    """
    now = now or utcnow()
    cfg = load_settings()

    pending = (
        Article.query.filter_by(status=ArticleStatus.PENDING)
        .order_by(Article.submitted_at.asc())
        .all()
    )
    depth = len(pending)
    oldest = hours_since(pending[0].submitted_at, now) if pending else 0.0

    result = {
        "open": triage.valve_open(queue_depth=depth, oldest_wait_hours=oldest, settings=cfg),
        "queueDepth": depth,
        "oldestWaitHours": round(oldest, 1),
        "published": [],
        "held": {},
    }
    if not result["open"]:
        return result

    limit = int({**triage.DEFAULTS, **cfg}["autopublish_max_per_run"])
    reason = f"queue {depth} pending, oldest waiting {oldest:.1f}h"

    for article in pending:
        if len(result["published"]) >= limit:
            break
        verdict = eligibility_for(article, cfg, now)
        if not verdict.eligible:
            result["held"][article.id] = verdict.reasons
            continue
        publish_article(article, reviewer_id=None, now=now, auto=True, detail=reason)
        result["published"].append(article.id)

    db.session.commit()
    return result


def suspend_after_correction(article: Article, now: datetime | None = None) -> bool:
    """Revoke auto-publish for a writer whose auto-published article was corrected.

    This is what makes a trust score expensive to spend. Without it, a writer
    could publish accurate work until eligible, then push one false story through
    unreviewed and carry on. With it, the first correction on anything that
    skipped review costs them the privilege. Does not commit.

    Returns whether a suspension was applied.
    """
    if article.auto_published_at is None:
        return False

    now = now or utcnow()
    days = float({**triage.DEFAULTS, **load_settings()}["autopublish_suspension_days"])
    writer = article.contributor
    writer.autopublish_suspended_until = now + timedelta(days=days)

    db.session.add(
        AuditLog(
            actor_id=None,
            action="user.autopublish_suspended",
            entity_type="user",
            entity_id=writer.id,
            detail=f"correction on auto-published article {article.id}, {days:g} days",
        )
    )
    return True


def lift_suspension_if_cleared(writer: User) -> bool:
    """Lift a suspension once no correction that could have caused it still stands.

    A writer who wins a dispute has had the correction overturned; a suspension
    that outlived the correction behind it would punish them for an error the
    platform has since said they did not make. The suspension stays while any
    correction on any of their auto-published articles is still in force.
    Does not commit; call after the overturn has been flushed.

    Returns whether a suspension was lifted.
    """
    if writer.autopublish_suspended_until is None:
        return False

    # Imported here for the same reason as has_duplicate_title.
    from .models import Correction

    standing = (
        db.session.query(func.count(Correction.id))
        .join(Article, Article.id == Correction.article_id)
        .filter(
            Article.contributor_id == writer.id,
            Article.auto_published_at.isnot(None),
            Correction.overturned_at.is_(None),
        )
        .scalar()
        or 0
    )
    if standing:
        return False

    writer.autopublish_suspended_until = None
    db.session.add(
        AuditLog(
            actor_id=None,
            action="user.autopublish_restored",
            entity_type="user",
            entity_id=writer.id,
            detail="every correction behind the suspension has been overturned",
        )
    )
    return True
