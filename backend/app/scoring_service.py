"""Database-facing wrapper around the pure engine in `credibility.py`.

The engine itself does no I/O so it can be unit-tested in isolation (PRD 7.5.1).
This module is the only place that reads inputs from the database and writes the
denormalised results back.

Triggers, per PDD Section 3: Article Management calls `rescore_article` on publish
and whenever an input changes; Moderation calls it when a correction or retraction
is logged, or when a report is upheld.
"""
from __future__ import annotations

from sqlalchemy import func

from . import credibility
from .enums import ArticleStatus, ReportStatus
from .extensions import db
from .models import Article, Correction, PlatformSetting, Report, User


def load_settings() -> dict[str, float]:
    """Admin overrides, merged over the shipped defaults by the engine itself."""
    return {row.key: row.value for row in PlatformSetting.query.all()}


def _published_counts(contributor_id: int) -> tuple[int, int]:
    """(published articles, of which corrected or retracted)."""
    published = (
        db.session.query(func.count(Article.id))
        .filter(
            Article.contributor_id == contributor_id,
            Article.status.in_([ArticleStatus.PUBLISHED, ArticleStatus.RETRACTED]),
        )
        .scalar()
        or 0
    )

    # An article counts as blemished if it was retracted, or carries at least one
    # correction that has not been overturned on appeal (PRD 1.3.2, admin power 4).
    blemished = (
        db.session.query(func.count(func.distinct(Article.id)))
        .outerjoin(Correction, Correction.article_id == Article.id)
        .filter(
            Article.contributor_id == contributor_id,
            Article.status.in_([ArticleStatus.PUBLISHED, ArticleStatus.RETRACTED]),
            db.or_(
                Article.status == ArticleStatus.RETRACTED,
                Correction.overturned_at.is_(None) & Correction.id.isnot(None),
            ),
        )
        .scalar()
        or 0
    )

    return published, blemished


def recalculate_accuracy(contributor: User, settings: dict | None = None) -> float | None:
    """Recompute and persist a contributor's Accuracy Rate. Returns it (or None)."""
    cfg = settings if settings is not None else load_settings()
    published, blemished = _published_counts(contributor.id)

    rate = credibility.accuracy_rate(published, blemished, cfg)
    contributor.accuracy_rate = rate
    return rate


def rescore_article(article: Article, settings: dict | None = None):
    """Recompute and persist one article's Credibility Score.

    Returns the ScoreBreakdown so the caller can hand the disclosure to the client
    without a second computation.
    """
    cfg = settings if settings is not None else load_settings()

    # Two different figures on purpose. `recalculate_accuracy` persists the
    # public rate, which is withheld below the minimum article count. The score
    # uses the same curve without that cutoff, so a contributor crossing the
    # minimum does not shift their whole back catalogue in one step.
    published_rate = recalculate_accuracy(article.contributor, cfg)
    published, blemished = _published_counts(article.contributor_id)
    accuracy = credibility.smoothed_accuracy(published, blemished, cfg)

    valid_sources = sum(1 for s in article.sources if s.is_valid)
    corrections = sum(1 for c in article.corrections if c.overturned_at is None)
    upheld_reports = (
        db.session.query(func.count(Report.id))
        .filter(Report.article_id == article.id, Report.status == ReportStatus.UPHELD)
        .scalar()
        or 0
    )

    result = credibility.credibility_score(
        contributor_accuracy=accuracy,
        source_count=valid_sources,
        correction_count=corrections,
        is_retracted=article.is_retracted,
        upheld_report_count=upheld_reports,
        settings=cfg,
        accuracy_withheld=published_rate is None,
    )

    article.credibility_score = result.score
    article.credibility_band = result.band
    return result


def explain_article(article: Article, settings: dict | None = None):
    """Recompute one article's score WITHOUT persisting anything.

    The reader-facing disclosure needs the arithmetic, not just the total, and a
    GET must never write. This reads the same inputs `rescore_article` does and
    runs the same pure function over them, so the ledger a reader sees and the
    number stored on the row cannot drift apart.
    """
    cfg = settings if settings is not None else load_settings()

    published, blemished = _published_counts(article.contributor_id)
    accuracy = credibility.smoothed_accuracy(published, blemished, cfg)

    upheld = (
        db.session.query(func.count(Report.id))
        .filter(Report.article_id == article.id, Report.status == ReportStatus.UPHELD)
        .scalar()
        or 0
    )

    return credibility.credibility_score(
        contributor_accuracy=accuracy,
        source_count=sum(1 for s in article.sources if s.is_valid),
        correction_count=sum(1 for c in article.corrections if c.overturned_at is None),
        is_retracted=article.is_retracted,
        upheld_report_count=upheld,
        settings=cfg,
        accuracy_withheld=credibility.accuracy_rate(published, blemished, cfg) is None,
    )


def rescore_contributor_articles(contributor: User) -> None:
    """A contributor's accuracy feeds every one of their articles.

    So a correction on one article moves the score of all of them, and we
    recompute the set in a single transaction rather than leaving the others
    stale.
    """
    cfg = load_settings()
    recalculate_accuracy(contributor, cfg)

    articles = Article.query.filter(
        Article.contributor_id == contributor.id,
        Article.status.in_([ArticleStatus.PUBLISHED, ArticleStatus.RETRACTED]),
    ).all()

    for article in articles:
        rescore_article(article, cfg)
